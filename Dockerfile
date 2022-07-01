FROM rackspacedot/python37
LABEL  MAINTAINER="xunhanliu<1638081534@qq.com>"
# 修改时区、 pip>10 可以config 换源
RUN echo "Asia/Shanghai" >  /etc/timezone \
    && pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple/ \
    &&  python -m pip install --upgrade pip



RUN mkdir -p /usr/src/middleware

WORKDIR /usr/src

COPY es_sync .
COPY run.py .

ADD requirements.txt /usr/src
RUN pip install -r /usr/src/requirements.txt
CMD ["python","run.py", "config.yaml"]
# docker build 示例： docker build -t py-mysql-elasticsearch-sync:latest .