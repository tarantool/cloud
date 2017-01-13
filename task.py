#!/usr/bin/env python

import uuid
import datetime
import gevent
import logging

STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_WARNING = "warning"
STATUS_CRITICAL = "error"


STATUSES = [STATUS_SUCCESS, STATUS_WARNING, STATUS_CRITICAL, STATUS_RUNNING]

class Task(object):
    def __init__(self, task_type):
        self.task_id = uuid.uuid4().hex
        self.task_type = task_type
        self.index = 0
        self.logs = []
        self.progress = 0
        self.status = STATUS_RUNNING
        self.message = ""
        self.event = gevent.event.Event()

    def log(self, msg, *args, **kwargs):
        progress = kwargs.get('progress', None)
        message = str(msg)
        if args:
            message = message % args

        logging.info("TASK: %s", message)

        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

        if progress is not None:
            self.progress = progress

        self.index += 1
        self.logs.append({
            "timestamp": timestamp,
            "progress": self.progress,
            "message": message,
            "index": self.index
        })
        self.notify()

    def get_index(self):
        return self.index

    def get_dict(self, index = None):
        logs = None
        if index:
            logs = []
            for log in self.logs:
                if log['index'] > index:
                    logs.append(log)
        else:
            logs = self.logs

        obj = {"id": self.task_id,
               "type": self.task_type,
               "status": self.status,
               "message": self.message,
               "index": self.index,
               "progress": self.progress,
               "logs": logs}

        return obj

    def wait(self, index, timeout=None):
        if self.index != index:
            return self.index

        self.event.wait(timeout)

        return self.index

    def wait_for_completion(self, timeout=None):
        index = 0

        while self.status == STATUS_RUNNING:
            index = self.wait(index, timeout)

    def notify(self):
        self.event.set()
        self.event.clear()

    def set_status(self, status, message=None):
        if status not in STATUSES:
            raise RuntimeError("Unknown status: '%s'" % status)

        self.status = status

        if message is not None:
            self.message = message

        self.index += 1
        self.notify()
