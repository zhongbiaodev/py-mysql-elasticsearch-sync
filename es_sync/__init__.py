from __future__ import print_function, unicode_literals
from future.builtins import str, range
import sys

PY2 = sys.version_info[0] == 2

if PY2:
    import os
    DEVNULL = open(os.devnull, 'wb')
else:
    from subprocess import DEVNULL


def encode_in_py2(s):
    if PY2:
        return s.encode('utf-8')
    return s

import os.path
import yaml
import signal
import requests
import subprocess
import json
import logging
import shlex
import datetime
from lxml.etree import iterparse
from functools import reduce
from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.row_event import DeleteRowsEvent, UpdateRowsEvent, WriteRowsEvent
from pymysqlreplication.event import RotateEvent

__version__ = '0.4.0'


# The magic spell for removing invalid characters in xml stream.
REMOVE_INVALID_PIPE = r'tr -d "\00\01\02\03\04\05\06\07\10\13\14\16\17\20\21\22\23\24\25\26\27\30\31\32\33\34\35\36\37"'

DEFAULT_BULKSIZE = 100
DEFAULT_BINLOG_BULKSIZE = 1


class ElasticSync(object):
    table_structure = {}
    log_file = None
    log_pos = None

    @property
    def is_binlog_sync(self):
        rv = bool(self.log_file and self.log_pos)
        return rv

    def __init__(self):
        try:
            self.config = yaml.load(open(sys.argv[1]))
        except IndexError:
            print('Error: not specify config file')
            exit(1)

        mysql = self.config.get('mysql')
        if mysql.get('table'):
            self.tables = [mysql.get('table')]
            self.dump_cmd = 'mysqldump -h {host} -P {port} -u {user} --password={password} {db} {table} ' \
                        '--default-character-set=utf8 -X --opt --quick'.format(**mysql)
        elif mysql.get('tables'):
            self.tables = mysql.get('tables')
            mysql.update({
                'tables': ' '.join(mysql.get('tables'))
            })
            self.dump_cmd = 'mysqldump -h {host} -P {port} -u {user} --password={password} --database {db} --tables {tables} ' \
                        '--default-character-set=utf8 -X --opt --quick'.format(**mysql)
        else:
            print('Error: must specify either table or tables')
            exit(1)
        self.master = self.tables[0]  # use the first table as master
        self.current_table = None

        self.binlog_conf = dict(
            [(key, self.config['mysql'][key]) for key in ['host', 'port', 'user', 'password', 'db']]
        )

        self.endpoint = 'http://{host}:{port}/{index}/{type}/_bulk'.format(
            host=self.config['elastic']['host'],
            port=self.config['elastic']['port'],
            index=self.config['elastic']['index'],
            type=self.config['elastic']['type']
        )  # todo: supporting multi-index

        self.mapping = self.config.get('mapping') or {}
        if self.mapping.get('_id'):
            self.id_key = self.mapping.pop('_id')
        else:
            self.id_key = None

        self.ignoring = self.config.get('ignoring') or []

        record_path = self.config['binlog_sync']['record_file']
        if os.path.isfile(record_path):
            with open(record_path, 'r') as f:
                record = yaml.load(f)
                self.log_file = record.get('log_file')
                self.log_pos = record.get('log_pos')

        self.bulk_size = self.config.get('elastic').get('bulk_size') or DEFAULT_BULKSIZE
        self.binlog_bulk_size = self.config.get('elastic').get('binlog_bulk_size') or DEFAULT_BINLOG_BULKSIZE

        self._init_logging()

    def _init_logging(self):
        logging.basicConfig(filename=self.config['logging']['file'],
                            level=logging.INFO,
                            format='[%(levelname)s] %(asctime)s %(message)s')
        self.logger = logging.getLogger(__name__)
        logging.getLogger("requests").setLevel(logging.WARNING)  # disable requests info logging

        def cleanup(*args):
            self.logger.info('Received stop signal')
            self.logger.info('Shutdown')
            sys.exit(0)

        signal.signal(signal.SIGINT, cleanup)
        signal.signal(signal.SIGTERM, cleanup)

    def _post_to_es(self, data):
        """
        send post requests to es restful api
        """
        resp = requests.post(self.endpoint, data=data)
        if resp.json().get('errors'):  # a boolean to figure error occurs
            for item in resp.json()['items']:
                if list(item.values())[0].get('error'):
                    logging.error(item)
        else:
            self._save_binlog_record()

    def _bulker(self, bulk_size):
        """
        Example:
            u = bulker()
            u.send(None)  #for generator initialize
            u.send(json_str)  # input json item
            u.send(another_json_str)  # input json item
            ...
            u.send(None) force finish bulk and post
        """
        while True:
            data = ""
            for i in range(bulk_size):
                item = yield
                if item:
                    data = data + item + "\n"
                else:
                    break
            # print(data)
            print('-'*10)
            if data:
                self._post_to_es(data)

    def _updater(self, data):
        """
        encapsulation of bulker
        """
        if self.is_binlog_sync:
            u = self._bulker(bulk_size=self.binlog_bulk_size)
        else:
            u = self._bulker(bulk_size=self.bulk_size)

        u.send(None)  # push the generator to first yield
        for item in data:
            u.send(item)
        u.send(None)  # tell the generator it's the end

    def _json_serializer(self, obj):
        """
        format the object which json not supported
        """
        if isinstance(obj, datetime.datetime) or isinstance(obj, datetime.date):
            return obj.isoformat()
        raise TypeError('Type not serializable')

    def _processor(self, data):
        """
        The action must be one of the following:
        create
            Create a document only if the document does not already exist.
        index
            Create a new document or replace an existing document.
        update
            Do a partial update on a document.
        delete
            Delete a document.
        """
        for item in data:
            if self.id_key:
                action_content = {'_id': item['doc'][self.id_key]}
            else:
                action_content = {}
            for field in self.ignoring:
                try:
                    item['doc'].pop(field)
                except KeyError:
                    pass
            meta = json.dumps({item['action']: action_content})
            if item['action'] == 'index':
                body = json.dumps(item['doc'], default=self._json_serializer)
                rv = meta + '\n' + body
            elif item['action'] == 'update':
                body = json.dumps({'doc': item['doc']}, default=self._json_serializer)
                rv = meta + '\n' + body
            elif item['action'] == 'delete':
                rv = meta + '\n'
            elif item['action'] == 'create':
                body = json.dumps(item['doc'], default=self._json_serializer)
                rv = meta + '\n' + body
            else:
                logging.error('unknown action type in doc')
                raise TypeError('unknown action type in doc')
            yield rv

    def _mapper(self, data):
        """
        mapping old key to new key
        """
        for item in data:
            if self.mapping:
                for k, v in self.mapping.items():
                    item['doc'][k] = item['doc'][v]
                    del item['doc'][v]
            # print(doc)
            yield item

    def _formatter(self, data):
        """
        format every field from xml, according to parsed table structure
        """
        for item in data:
            for field, serializer in self.table_structure.items():
                if field in item['doc'] and item['doc'][field]:
                    try:
                        item['doc'][field] = serializer(item['doc'][field])
                    except ValueError as e:
                        self.logger.error(
                            "Error occurred during format, ErrorMessage:{msg}, ErrorItem:{item}".format(
                            msg=str(e),
                            item=str(item)))
                        item['doc'][field] = None
            # print(item)
            yield item

    def _binlog_loader(self):
        """
        read row from binlog
        """
        if self.is_binlog_sync:
            resume_stream = True
            logging.info("Resume from binlog_file: {file}  binlog_pos: {pos}".format(file=self.log_file,
                                                                                     pos=self.log_pos))
        else:
            resume_stream = False

        stream = BinLogStreamReader(connection_settings=self.binlog_conf,
                                    server_id=self.config['mysql']['server_id'],
                                    only_events=[DeleteRowsEvent, WriteRowsEvent, UpdateRowsEvent, RotateEvent],
                                    only_tables=self.tables,
                                    resume_stream=resume_stream,
                                    blocking=True,
                                    log_file=self.log_file,
                                    log_pos=self.log_pos)
        for binlogevent in stream:
            self.log_file = stream.log_file
            self.log_pos = stream.log_pos

            # RotateEvent to update binlog record when no related table changed
            if isinstance(binlogevent, RotateEvent):
                self._save_binlog_record()
                continue
            for row in binlogevent.rows:
                if isinstance(binlogevent, DeleteRowsEvent):
                    if binlogevent.table == self.master:
                        rv = {
                            'action': 'delete',
                            'doc': row['values']
                        }
                    else:
                        rv = {
                            'action': 'update',
                            'doc': {k: row['values'][k] if self.id_key and self.id_key == k else None for k in row['values']}
                        }
                elif isinstance(binlogevent, UpdateRowsEvent):
                    rv = {
                        'action': 'update',
                        'doc': row['after_values']
                    }
                elif isinstance(binlogevent, WriteRowsEvent):
                    if binlogevent.table == self.master:
                        rv = {
                                'action': 'create',
                                'doc': row['values']
                            }
                    else:
                        rv = {
                                'action': 'update',
                                'doc': row['values']
                            }
                else:
                    logging.error('unknown action type in binlog')
                    raise TypeError('unknown action type in binlog')
                yield rv
                # print(rv)
        stream.close()
        raise IOError('mysql connection closed')

    def _parse_table_structure(self, data):
        """
        parse the table structure
        """
        for item in data.iter():
            if item.tag == 'field':
                field = item.attrib.get('Field')
                type = item.attrib.get('Type')
                if 'int' in type:
                    serializer = int
                elif 'float' in type:
                    serializer = float
                elif 'datetime' in type:
                    if '(' in type:
                        serializer = lambda x: datetime.datetime.strptime(x, '%Y-%m-%d %H:%M:%S.%f')
                    else:
                        serializer = lambda x: datetime.datetime.strptime(x, '%Y-%m-%d %H:%M:%S')
                elif 'char' in type:
                    serializer = str
                elif 'text' in type:
                    serializer = str
                else:
                    serializer = str
                self.table_structure[field] = serializer

    def _parse_and_remove(self, f, path):
        """
        snippet from python cookbook, for parsing large xml file
        """
        path_parts = path.split('/')
        doc = iterparse(f, ('start', 'end'), recover=False, encoding='utf-8', huge_tree=True)
        # Skip the root element
        next(doc)
        tag_stack = []
        elem_stack = []
        for event, elem in doc:
            if event == 'start':
                if elem.tag == 'table_data':
                    self.current_table = elem.attrib['name']
                tag_stack.append(elem.tag)
                elem_stack.append(elem)
            elif event == 'end':
                if tag_stack == ['database', 'table_data']:
                    self.current_table = None
                if tag_stack == path_parts:
                    yield elem
                    elem_stack[-2].remove(elem)
                if tag_stack == ['database', 'table_structure']:
                # dirty hack for getting the tables structure
                    self._parse_table_structure(elem)
                    elem_stack[-2].remove(elem)
                try:
                    tag_stack.pop()
                    elem_stack.pop()
                except IndexError:
                    pass

    def _xml_parser(self, f_obj):
        """
        parse mysqldump XML streaming, convert every item to dict object.
        'database/table_data/row'
        """
        for row in self._parse_and_remove(f_obj, 'database/table_data/row'):
            doc = {}
            for field in row.iter(tag='field'):
                k = field.attrib.get('name')
                v = field.text
                doc[k] = v
            if not self.current_table or self.current_table == self.master:
                yield {'action': 'create', 'doc': doc}
            else:
                yield {'action': 'update', 'doc': doc}

    def _save_binlog_record(self):
        if self.is_binlog_sync:
            with open(self.config['binlog_sync']['record_file'], 'w') as f:
                logging.info("Sync binlog_file: {file}  binlog_pos: {pos}".format(
                    file=self.log_file,
                    pos=self.log_pos)
                )
                yaml.safe_dump({"log_file": self.log_file,
                                "log_pos": self.log_pos},
                               f,
                               default_flow_style=False)

    def _xml_dump_loader(self):
        mysqldump = subprocess.Popen(
            shlex.split(encode_in_py2(self.dump_cmd)),
            stdout=subprocess.PIPE,
            stderr=DEVNULL,
            close_fds=True)

        remove_invalid_pipe = subprocess.Popen(
            shlex.split(encode_in_py2(REMOVE_INVALID_PIPE)),
            stdin=mysqldump.stdout,
            stdout=subprocess.PIPE,
            stderr=DEVNULL,
            close_fds=True)

        return remove_invalid_pipe.stdout

    def _xml_file_loader(self, filename):
        f = open(filename, 'rb')  # bytes required

        remove_invalid_pipe = subprocess.Popen(
            shlex.split(encode_in_py2(REMOVE_INVALID_PIPE)),
            stdin=f,
            stdout=subprocess.PIPE,
            stderr=DEVNULL,
            close_fds=True)
        return remove_invalid_pipe.stdout

    def _send_email(self, title, content):
        """
        send notification email
        """
        if not self.config.get('email'):
            return

        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(content)
        msg['Subject'] = title
        msg['From'] = self.config['email']['from']['username']
        msg['To'] = ', '.join(self.config['email']['to'])

        # Send the message via our own SMTP server.
        s = smtplib.SMTP()
        s.connect(self.config['email']['from']['host'])
        s.login(user=self.config['email']['from']['username'],
                password=self.config['email']['from']['password'])
        s.sendmail(msg['From'], msg['To'], msg=msg.as_string())
        s.quit()

    def _sync_from_stream(self):
        logging.info("Start to dump from stream")
        docs = reduce(lambda x, y: y(x), [self._xml_parser, 
                                          self._formatter,
                                          self._mapper, 
                                          self._processor], 
                      self._xml_dump_loader())
        self._updater(docs)
        logging.info("Dump success")

    def _sync_from_file(self):
        logging.info("Start to dump from xml file")
        logging.info("Filename: {}".format(self.config['xml_file']['filename']))
        docs = reduce(lambda x, y: y(x), [self._xml_parser, 
                                          self._formatter, 
                                          self._mapper, 
                                          self._processor],
                      self._xml_file_loader(self.config['xml_file']['filename']))
        self._updater(docs)
        logging.info("Dump success")

    def _sync_from_binlog(self):
        logging.info("Start to sync binlog")
        docs = reduce(lambda x, y: y(x), [self._mapper,
                                          self._processor],
                      self._binlog_loader())
        self._updater(docs)

    def run(self):
        """
        workflow:
        1. sync dump data
        2. sync binlog
        """
        try:
            if not self.is_binlog_sync:
                if len(sys.argv) > 2 and sys.argv[2] == '--fromfile':
                    self._sync_from_file()
                else:
                    self._sync_from_stream()
            self._sync_from_binlog()
        except Exception:
            import traceback
            logging.error(traceback.format_exc())
            self._send_email('es sync error', traceback.format_exc())
            raise


def start():
    instance = ElasticSync()
    instance.run()

if __name__ == '__main__':
    start()
