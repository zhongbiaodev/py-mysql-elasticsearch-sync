# py-mysql-elasticsearch-sync
Simple and fast MySQL to Elasticsearch sync tool, written in Python3.

## Introduction
This tool helps you to initialize MySQL dump table to Elasticsearch by parsing mysqldump, then incremental sync MySQL table to Elasticsearch by processing MySQL Binlog.

## Installation
This tool is written in Python3.4, so you must install Python3.4 first, by following [this guide](https://docs.python.org/3.4/using/index.html)

Also, this tool depends on python lxml package, in which you should install it correctly. (Attention, the lxml needs )
See [lxml Installation](http://lxml.de/installation.html) 

Then clone this repo and install dependencies

```
git clone https://github.com/zhongbiaodev/py-mysql-elasticsearch-sync.git 

cd py-mysql-elasticsearch-sync

pip install -r requirements.txt
```

## Configuration
TODO

## Deployment and Running
TODO


## TODO
- [ ]  Documentation
- [ ]  Packaging
- [ ]  MultiIndex Supporting

