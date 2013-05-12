#!/usr/bin/env python
#
# Copyright 2012 Brett Slatkin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Background mapreduce and periodic jobs."""

import datetime
import logging
import time

from google.appengine.ext import webapp

# Local libs
import config
from mapreduce import context
from mapreduce import operation
from mapreduce import mapreduce_pipeline
from mapreduce.lib import pipeline
import models


# TODO(bslatkin): Use an upstream version of this instead.
class DeleteNdb(operation.Operation):
    """Delete entity from ndb via mutation_pool."""

    def __init__(self, entity):
        self.entity = entity

    def __call__(self, context):
        context.mutation_pool.ndb_delete(self.entity)


class DeleteOldPostsMapper(object):
    """Mapper for deleting old posts."""

    def __init__(self):
        ctx = context.get()
        when = ctx.mapreduce_spec.mapper.params.get(
            'before_timestamp_seconds')
        assert when
        self.before_datetime = datetime.datetime.utcfromtimestamp(when)

    def map(self, entity):
        if entity.post_time < self.before_datetime:
            yield operation.counters.Increment('deleted_post')
            yield DeleteNdb(entity)


class DeleteOldPostsPipeline(pipeline.Pipeline):
    """Delete old posts that have expired."""

    def run(self, lifetime_seconds=None):
        if lifetime_seconds is None:
            lifetime_seconds = config.ephemeral_lifetime_seconds
        now = time.time()
        before_timestamp_seconds = now - lifetime_seconds

        # TODO(bslatkin): Also clean up old PostRecord entities, Shards,
        # LoginRecords; anything with an update time. But do not delete Posts
        # or PostRecords being used for Topics until they have been inactive
        # for more than 30 days.

        yield mapreduce_pipeline.MapperPipeline(
            'Delete old posts',
            'jobs.DeleteOldPostsMapper.map',
            'mapreduce.input_readers.DatastoreInputReader',
            params=dict(entity_kind='models.Post',
                        before_timestamp_seconds=before_timestamp_seconds),
            shards=8)


class PeriodicHandler(webapp.RequestHandler):
    """Handler for periodically kicking off pipelines."""

    def get(self):
        key = self.request.get('key')
        day_string = datetime.datetime.now().strftime('%Y-%m-%d')
        idempotence_key = '%s-%s' % (key, day_string)

        job = DeleteOldPostsPipeline()
        job.start(idempotence_key=idempotence_key,
                  queue_name='jobs')
        logging.info('Started DeleteOldPostsPipeline with pipeline_id=%r',
                     job.pipeline_id)


ROUTES = [
    (r'/jobs/periodic', PeriodicHandler),
]
