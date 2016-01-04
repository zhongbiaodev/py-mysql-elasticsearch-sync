# py-mysql-elasticsearch-sync
Simple and fast MySQL to Elasticsearch sync tool, written in Python3.

## Introduction
This tool helps you to initialize MySQL dump table to Elasticsearch by parsing mysqldump, then incremental sync MySQL table to Elasticsearch by processing MySQL Binlog.
Also, during the binlog syncing, this tool will save the binlog sync position, so that it is easy to recover after this tool being shutdown for any reason.

## Installation
By following these steps.
##### 1. Python3
This tool is written in Python3.4, so you must install Python3.4 or above first, by following [this guide](https://docs.python.org/3.4/using/index.html)
##### 2. ibxml2 and libxslt
Also, this tool depends on python lxml package, so that you should install  the lxml's dependecies correctly, the libxml2 and libxslt are required.

For example, in CentOS:

```
sudo yum install libxml2 libxml2-devel libxslt libxslt-devel
```

Or in Debian/Ubuntu:

```
sudo apt-get install libxml2-dev libxslt-dev python-dev
```

See [lxml Installation](http://lxml.de/installation.html) for more infomation.
##### 3. mysqldump
And then, mysqldump is required.


##### 4. this tool
Then install this tool

```
pip3 install py-mysql-elasticsearch-sync
```

## Configuration
There is a [sample config](https://github.com/zhongbiaodev/py-mysql-elasticsearch-sync/blob/master/sample.yaml) file in repo, you can start by editing it.

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
We provide an upstart script to help you deploy this tool,since we use virtualenv for requirements isolation, you must edit it for your own condition, besides, you can deploy it in your own way.


## TODO
- [ ] MultiIndex Supporting
- [ ] Multi table Supporting
- [ ] Python version compat
