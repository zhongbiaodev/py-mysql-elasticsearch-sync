# py-mysql-elasticsearch-sync
Simple and fast MySQL to Elasticsearch sync tool, written in Python.

[中文文档](https://github.com/zhongbiaodev/py-mysql-elasticsearch-sync/blob/master/README_CN.md)

## Introduction
This tool helps you to initialize MySQL dump table to Elasticsearch by parsing mysqldump, then incremental sync MySQL table to Elasticsearch by processing MySQL Binlog.
Also, during the binlog syncing, this tool will save the binlog sync position, so that it is easy to recover after this tool being shutdown for any reason.

## Installation
By following these steps.

##### 1. ibxml2 and libxslt
This tool depends on python lxml package, so that you should install  the lxml's dependecies correctly, the libxml2 and libxslt are required.

For example, in CentOS:

```
sudo yum install libxml2 libxml2-devel libxslt libxslt-devel
```

Or in Debian/Ubuntu:

```
sudo apt-get install libxml2-dev libxslt-dev python-dev
```

See [lxml Installation](http://lxml.de/installation.html) for more infomation.
##### 2. mysqldump
And then, mysqldump is required in the machine where this tool will be run on it.(and the mysql server must enable binlog)


##### 3. this tool
Then install this tool

```
pip install py-mysql-elasticsearch-sync
```

## Configuration
There is a [sample config](https://github.com/zhongbiaodev/py-mysql-elasticsearch-sync/blob/master/es_sync/sample.yaml) file in repo, you can start by editing it.

## Running
Simply run command

```
es-sync path/to/your/config.yaml
```
and the tool will dump your data as stream to sync, when dump is over, it will start to sync binlog.

The latest synced binlog file and position are recorded in your info file which is configured in your config file. You can restart dump step by remove it, or you can change sync position by edit it.

Or if you  but want to load it from your own dumpfile. You should dump your table first as xml format(by adding ```-X```option to your mysqldump command) 

then

```
es-sync path/to/your/config.yaml --fromfile
```
to start sync, when xml sync is over, it will also start binlog sync.

## Deployment
We provide an [upstart script]((https://github.com/zhongbiaodev/py-mysql-elasticsearch-sync/blob/master/upstart.conf)) to help you deploy this tool, you can edit it for your own condition, besides, you can deploy it in your own way.

## MultiTable Supporting
Now Multi-table is supported through setting tables in config file, the first table is master as default and the others are slave.

Master table and slave tables must use the same primary key, which is defined via _id.

Table has higher priority than tables.

## TODO
- [ ] MultiIndex Supporting
