# py-mysql-elasticsearch-sync
一个从MySQL向Elasticsearch同步数据的工具，使用Python实现。

## 简介
在第一次初始化数据时，本工具解析mysqldump导出的数据，并导入ES中，在后续增量更新中，解析binlog的数据，对ES中的数据进行同步。在binlog同步阶段，支持断点恢复，因此无需担心意外中断的问题。

## 安装

##### 1. ibxml2 和 libxslt
本工具基于lxml库，因此需要安装它的依赖的libxml2和libxslt

在CentOS中:

```
sudo yum install libxml2 libxml2-devel libxslt libxslt-devel
```

在Debian/Ubuntu中:

```
sudo apt-get install libxml2-dev libxslt-dev python-dev
```

查看[lxml Installation](http://lxml.de/installation.html)来获取更多相关信息

##### 2. mysqldump
在运行本工具的机器上需要有mysqldump，并且mysql服务器需要开启binlog功能。


##### 3. 本工具
安装本工具

```
pip install py-mysql-elasticsearch-sync
```

## 配置
你可以通过修改[配置文件示例](https://github.com/zhongbiaodev/py-mysql-elasticsearch-sync/blob/master/es_sync/sample.yaml)来编写自己的配置文件

## 运行
运行命令

```
es-sync path/to/your/config.yaml
```
工具将开始执行mysqldump并解析流进行同步，当dump结束后，将启动binlog同步

最近一次binlog同步位置记录在一个文件中，这个文件的路径在config文件中配置过。

你可以删除记录文件来从头进行binlog同步，或者修改文件里的内容，来从特定位置开始同步。


你也可以把自己从mysql导出的xml文件同步进ES中(在mysqldump的命令中加上参数```-X```即可导出xml) 

然后执行

```
es-sync path/to/your/config.yaml --fromfile
```
启动从xml导入，当从xml导入完毕后，它会开始同步binlog

## 服务管理
我们写了一个[upstart脚本](https://github.com/zhongbiaodev/py-mysql-elasticsearch-sync/blob/master/upstart.conf)来管理本工具的运行，你也可以用你自己的方式进行部署运行

## TODO
- [ ] 多索引支持
- [ ] 多表支持
