#!/usr/bin/env python3

import global_env
import consul
import uuid
import os
import gzip
import hashlib
import datetime
import task
import sense
import logging

CHUNK_SIZE = 1024 ** 2


class BackupTask(task.Task):
    backup_task_type = None

    def __init__(self, backup_id):
        super().__init__(self.backup_task_type)
        self.backup_id = backup_id

    def get_dict(self, index=None):
        obj = super().get_dict(index)
        obj['backup_id'] = self.backup_id
        return obj


class DeleteTask(BackupTask):
    backup_task_type = "delete_backup"


class BackupRegistry(object):
    def __init__(self):
        pass

    def register(self, group_id, backup_id):
        pass

    def list(self, group_id):
        pass

    def list_all(self):
        pass


class BackupStorage(object):
    backup_storage_type = None

    def put_archive(self, stream):
        raise NotImplementedError()

    def get_archive(self, digest):
        raise NotImplementedError()

    def delete_archive(self, digest):
        raise NotImplementedError()

    def register_backup(self, backup_id, archive_id, instance_type,
                        size, mem_used):
        consul_obj = consul.Consul(host=global_env.consul_host,
                                   token=global_env.consul_acl_token)
        kv = consul_obj.kv

        creation_time = datetime.datetime.now(
            datetime.timezone.utc).isoformat()

        kv.put('tarantool_backups/%s/type' % backup_id, instance_type)
        kv.put('tarantool_backups/%s/archive_id' % backup_id, archive_id)
        kv.put('tarantool_backups/%s/creation_time' % backup_id, creation_time)
        kv.put('tarantool_backups/%s/storage' % backup_id,
               self.backup_storage_type)
        kv.put('tarantool_backups/%s/size' % backup_id,
               str(size))
        kv.put('tarantool_backups/%s/mem_used' % backup_id,
               str(mem_used))

        return backup_id

    def unregister_backup(self, backup_id, delete_task):
        try:
            consul_obj = consul.Consul(host=global_env.consul_host,
                                       token=global_env.consul_acl_token)
            kv = consul_obj.kv

            delete_task.log("Unregistring backup '%s'", backup_id)

            backup = sense.Sense.backups()[backup_id]
            archive_id = backup['archive_id']

            kv.delete('tarantool_backups/%s' % backup_id, recurse=True)

            sense.Sense.update()

            archive_used = False
            for backup in sense.Sense.backups().values():
                if backup['archive_id'] == archive_id:
                    archive_used = True

            if archive_used:
                delete_task.log(
                    "Backup '%s' has archive '%s' that is used by " +
                    "other backups. Keeping it.", (backup_id, archive_id))
            else:
                delete_task.log(
                    "Archive no longer used: '%s'. Removing it.", archive_id)
                self.delete_archive(archive_id)

            delete_task.set_status(task.STATUS_SUCCESS)
        except Exception as ex:
            logging.exception("Failed to unregister backup '%s'", backup_id)
            task.set_status(delete_task.STATUS_CRITICAL, str(ex))

            raise



class FilesystemBackupStorage(BackupStorage):
    backup_storage_type = "filesystem"

    def __init__(self, base_dir):
        self.base_dir = base_dir

    def put_archive(self, stream):
        archive_id = uuid.uuid4().hex

        tmp_path = os.path.join(self.base_dir, archive_id + '_pending.tar.gz')

        sha256 = hashlib.new('sha256')

        # Files must have predictable hashes, so timestamp has to be
        # set to a constant. It is written to the gzip stream.
        with gzip.GzipFile(tmp_path, 'wb', mtime=0) as fobj:
            for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
                fobj.write(chunk)

        total_size = 0
        with open(tmp_path, 'rb') as fobj:
            for chunk in iter(lambda: fobj.read(CHUNK_SIZE), b""):
                total_size += len(chunk)
                sha256.update(chunk)

        digest = sha256.hexdigest()

        fullpath = os.path.join(self.base_dir, digest + '.tar.gz')
        os.rename(tmp_path, fullpath)

        return digest, total_size

    def get_archive(self, digest):
        fullpath = os.path.join(self.base_dir, digest + '.tar.gz')

        return gzip.GzipFile(fullpath, 'rb')

    def delete_archive(self, digest):
        fullpath = os.path.join(self.base_dir, digest + '.tar.gz')

        try:
            os.remove(fullpath)
        except OSError:
            pass
