#!/usr/bin/env python
# -*- encoding: utf-8 -*-
'''
@File    :   keyword.py
@License :   (C)Copyright 2022 , 社交数字人
'''


def process_id(item):
    """
    收到的数据是这样的。middleware 安排在了_mapping 后面怕
    {'action': 'create', 'doc': doc,"table":"XXX","es_index":"", "es_type":""}
    mapping old key to new key
    """
    # 把storage_t 重置为0
    item["doc"]["storage_t"]=100
    return item