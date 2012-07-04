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

"""Background workers for the 8-bits chat system."""

import datetime
import logging
## Useful to enable when testing in dev_appserver.
logging.getLogger().setLevel(logging.DEBUG)
import time
import wsgiref.handlers

from google.appengine.ext import webapp
from google.appengine.ext.appstats import recording

# Local libs
import config
from mapreduce import context
from mapreduce import operation
from mapreduce import mapreduce_pipeline
from mapreduce.lib import pipeline
import models
import ndb

################################################################################

class DeleteOldPostsMapper(object):
  """Mapper for deleting old posts."""

  def __init__(self):
    ctx = context.get()
    when = ctx.mapreduce_spec.mapper.params.get('before_timestamp_seconds')
    assert when
    self.before_datetime = datetime.datetime.utcfromtimestamp(when)

  def map(self, entity):
    if entity.post_time < self.before_datetime:
      yield operation.db.Delete(entity)


class DeleteOldPostsPipeline(pipeline.Pipeline):
  """Delete old posts that have expired."""

  def run(self, lifetime_seconds=None):
    if lifetime_seconds is None:
      lifetime_seconds = config.ephemeral_lifetime_seconds
    now = time.time()
    before_timestamp_seconds = now - lifetime_seconds

    yield mapreduce_pipeline.MapperPipeline(
        'Delete old posts',
        'jobs.DeleteOldPostsMapper',
        'google.appengine.ext.mapreduce.input_readers.DatastoreInputReader',
        params=dict(entity_kind='models.Post',
                    before_timestamp_seconds=before_timestamp_seconds),
        shards=8)

################################################################################

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

################################################################################

APP = webapp.WSGIApplication([
  (r'/jobs/periodic', PeriodicHandler),
], debug=config.debug)

## Enable appstats
# APP = recording.appstats_wsgi_middleware(APP)
