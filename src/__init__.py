import os.path
import sys
import yaml
import signal
import requests
import subprocess
import simplejson as json
import logging
import shlex
from datetime import datetime
from lxml.etree import iterparse
from functools import reduce
from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.row_event import DeleteRowsEvent, UpdateRowsEvent, WriteRowsEvent

__version__ = '0.2.0'


def cleanup(*args):
    logger.info('Received stop signal')
    logger.info('Shutdown')
    sys.exit(0)

signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

try:
    config = yaml.load(open(sys.argv[1]))
except IndexError:
    print('Error: not specify config file')
    exit(1)

logging.basicConfig(filename=config['logging']['file'],
                    level=logging.INFO,
                    format='[%(levelname)s] %(asctime)s %(message)s')
logger = logging.getLogger(__name__)
logging.getLogger("requests").setLevel(logging.WARNING)  # disable requests info logging

endpoint = 'http://{host}:{port}/{index}/{type}/_bulk'.format(host=config['elastic']['host'],
                                                              port=config['elastic']['port'],
                                                              index=config['elastic']['index'],
                                                              type=config['elastic']['type'])
                                                              # todo: supporting multi-index
MAPPING = config.get('mapping')
if MAPPING.get('_id'):
    id_key = MAPPING.pop('_id')
else:
    id_key = None

table_structure = {}

DUMP_CMD = 'mysqldump -h {host} -P {port} -u {user} --password={password} {db} {table} ' \
           '--default-character-set=utf8 -X'.format(**config['mysql'])

# For removing invalid characters in xml stream.
REMOVE_INVALID_PIPE = r'tr -d "\00\01\02\03\04\05\06\07\10\13\14\16\17\20\21\22\23\24\25\26\27\30\31\32\33\34\35\36\37"'

BINLOG_CFG = {key: config['mysql'][key] for key in ['host', 'port', 'user', 'password', 'db']}
BULK_SIZE = config.get('elastic').get('bulk_size')

log_file = None
log_pos = None

record_path = config['binlog_sync']['record_file']
if os.path.isfile(record_path):
    with open(record_path, 'r') as f:
        record = yaml.load(f)
        log_file = record.get('log_file')
        log_pos = record.get('log_pos')


def post_to_es(data):
    """
    send post requests to es restful api
    """
    resp = requests.post(endpoint, data=data)
    if resp.json().get('errors'):  # a boolean to figure error occurs
        for item in resp.json()['items']:
            if list(item.values())[0].get('error'):
                logging.error(item)
    else:
        save_binlog_record()


def bulker(bulk_size=BULK_SIZE):
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
            post_to_es(data)


def updater(data):
    """
    encapsulation of bulker
    """
    u = bulker()
    u.send(None)  # push the generator to first yield
    for item in data:
        u.send(item)
    u.send(None)  # tell the generator it's the end


def json_serializer(obj):
    """
    format the object which json not supported
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError('Type not serializable')


def processor(data):
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
        if id_key:
            action_content = {'_id': item['doc'][id_key]}
        else:
            action_content = {}
        meta = json.dumps({item['action']: action_content})
        if item['action'] == 'index':
            body = json.dumps(item['doc'], default=json_serializer)
            rv = meta + '\n' + body
        elif item['action'] == 'update':
            body = json.dumps({'doc': item['doc']}, default=json_serializer)
            rv = meta + '\n' + body
        elif item['action'] == 'delete':
            rv = meta + '\n'
        elif item['action'] == 'create':
            body = json.dumps(item['doc'], default=json_serializer)
            rv = meta + '\n' + body
        else:
            logging.error('unknown action type in doc')
            raise TypeError('unknown action type in doc')
        yield rv


def mapper(data):
    """
    mapping old key to new key
    """
    for item in data:
        for k, v in MAPPING.items():
            item['doc'][k] = item['doc'][v]
            del item['doc'][v]
        # print(doc)
        yield item


def formatter(data):
    """
    format every field from xml, according to parsed table structure
    """
    for item in data:
        for field, serializer in table_structure.items():
            if item['doc'][field]:
                try:
                    item['doc'][field] = serializer(item['doc'][field])
                except ValueError as e:
                    logger.error("Error occurred during format, ErrorMessage:{}, ErrorItem:{}".format(str(e),
                                                                                                      str(item)))
                    item['doc'][field] = None
        # print(item)
        yield item


def binlog_loader():
    """
    read row from binlog
    """
    global log_file
    global log_pos
    if log_file and log_pos:
        resume_stream = True
        logging.info("Resume from binlog_file: {}  binlog_pos: {}".format(log_file, log_pos))
    else:
        resume_stream = False

    stream = BinLogStreamReader(connection_settings=BINLOG_CFG, server_id=config['mysql']['server_id'],
                                only_events=[DeleteRowsEvent, WriteRowsEvent, UpdateRowsEvent],
                                only_tables=[config['mysql']['table']],
                                resume_stream=resume_stream,
                                blocking=True,
                                log_file=log_file,
                                log_pos=log_pos)
    for binlogevent in stream:
        log_file = stream.log_file
        log_pos = stream.log_pos
        for row in binlogevent.rows:
            if isinstance(binlogevent, DeleteRowsEvent):
                rv = {
                    'action': 'delete',
                    'doc': row['values']
                }
            elif isinstance(binlogevent, UpdateRowsEvent):
                rv = {
                    'action': 'update',
                    'doc': row['after_values']
                }
            elif isinstance(binlogevent, WriteRowsEvent):
                rv = {
                    'action': 'index',
                    'doc': row['values']
                }
            else:
                logging.error('unknown action type in binlog')
                raise TypeError('unknown action type in binlog')
            yield rv
            # print(rv)
    stream.close()


def parse_table_structure(data):
    """
    parse the table structure
    """
    global table_structure
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
                    serializer = lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S.%f')
                else:
                    serializer = lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S')
            elif 'char' in type:
                serializer = str
            elif 'text' in type:
                serializer = str
            else:
                serializer = str
            table_structure[field] = serializer


def parse_and_remove(f, path):
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
            tag_stack.append(elem.tag)
            elem_stack.append(elem)
        elif event == 'end':
            if tag_stack == path_parts:
                yield elem
                elem_stack[-2].remove(elem)
            if tag_stack == ['database', 'table_structure']:  # dirty hack for getting the tables structure
                parse_table_structure(elem)
                elem_stack[-2].remove(elem)
            try:
                tag_stack.pop()
                elem_stack.pop()
            except IndexError:
                pass


def xml_parser(f_obj):
    """
    parse mysqldump XML streaming, convert every item to dict object. 'database/table_data/row'
    """
    for row in parse_and_remove(f_obj, 'database/table_data/row'):
        doc = {}
        for field in row.iter(tag='field'):
            k = field.attrib.get('name')
            v = field.text
            doc[k] = v
        yield {'action': 'index', 'doc': doc}


def save_binlog_record():
    if log_file and log_pos:
        with open(config['binlog_sync']['record_file'], 'w') as f:
            logging.info("Sync binlog_file: {}  binlog_pos: {}".format(log_file, log_pos))
            yaml.dump({"log_file": log_file, "log_pos": log_pos}, f)


def xml_dump_loader():
    mysqldump = subprocess.Popen(
        shlex.split(DUMP_CMD),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        close_fds=True)

    remove_invalid_pipe = subprocess.Popen(
        shlex.split(REMOVE_INVALID_PIPE),
        stdin=mysqldump.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        close_fds=True)

    return remove_invalid_pipe.stdout


def xml_file_loader(filename):
    f = open(filename, 'rb')  # bytes required
    return f


def send_email(title, content):
    """
    send notification email
    """
    if not config.get('email'):
        return

    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(content)
    msg['Subject'] = title
    msg['From'] = config['email']['from']['username']
    msg['To'] = ', '.join(config['email']['to'])

    # Send the message via our own SMTP server.
    s = smtplib.SMTP()
    s.connect(config['email']['from']['host'])
    s.login(config['email']['from']['username'], config['email']['from']['password'])
    s.send_message(msg)
    s.quit()


def sync_from_stream():
    logging.info("Start to dump from stream")
    docs = reduce(lambda x, y: y(x), [xml_parser, formatter, mapper, processor], xml_dump_loader())
    updater(docs)
    logging.info("Dump success")


def sync_from_file():
    logging.info("Start to dump from xml file")
    docs = reduce(lambda x, y: y(x), [xml_parser, formatter, mapper, processor],
                  xml_file_loader(config['xml_file']['filename']))
    updater(docs)
    logging.info("Dump success")


def sync_from_binlog():
    logging.info("Start to sync binlog")
    docs = reduce(lambda x, y: y(x), [mapper, processor], binlog_loader())
    updater(docs)


def main():
    """
    workflow:
    1. sync dump data
    2. sync binlog
    """
    try:
        if not log_file and not log_pos:
            if len(sys.argv) > 2 and sys.argv[2] == '--fromfile':
                sync_from_file()
            else:
                sync_from_stream()
        sync_from_binlog()
    except Exception:
        import traceback
        logging.error(traceback.format_exc())
        send_email('es sync error', traceback.format_exc())
        raise


def run():
    main()

if __name__ == '__main__':
    main()
