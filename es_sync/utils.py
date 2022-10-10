#!/usr/bin/env python
# -*- encoding: utf-8 -*-
def ref_to_obj(ref):
    """
    Returns the object pointed to by ``ref``.

    :type ref: str

    """
    if not isinstance(ref, str):
        raise TypeError('References must be strings')
    if ':' not in ref:
        raise ValueError('Invalid reference')

    modulename, rest = ref.split(':', 1)
    try:
        obj = __import__(modulename, fromlist=[rest])
    except ImportError:
        a=10
        raise LookupError('Error resolving reference %s: could not import module' % ref)
    # except Exception as e:
    #     b=10
    #     a=100
    try:
        for name in rest.split('.'):
            obj = getattr(obj, name)
        return obj
    except Exception:
        raise LookupError('Error resolving reference %s: error looking up object' % ref)
