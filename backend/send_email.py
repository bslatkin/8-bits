#!/usr/bin/env python
#
# Copyright 2010 Brett Slatkin, Nathan Naze
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

"""Email notifications."""

import datetime
import logging

from google.appengine.api import mail
from google.appengine.api import taskqueue
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

# Local libs
import base
import config
import models
import ndb


def enqueue_email_tasks(emails_set):
  """Enqueues a set of email notification tasks for the given users.

  Notifies these users across multiple shards.

  Args:
    emails_set: Set of user email addresses to notify.
  """
  if not emails_set:
    logging.debug('No email addresses to notify')
    return

  logging.debug('Found %d email addresses to notify', len(emails_set))
  email_record_keys = [
      ndb.Key(models.EmailRecord._get_kind(), email_address)
      for email_address in emails_set]
  email_record_list = ndb.get_multi(email_record_keys)

  task_list = []
  for email_address, email_record in zip(emails_set, email_record_list):
    sequence_number = 1
    countdown = 0
    if email_record:
      sequence_number = email_record.sequence_number
      countdown = email_record.min_notify_period_seconds

    task = taskqueue.Task(
        url='/work/email_digest',
        params=dict(sequence_number=sequence_number,
                    email_address=email_address),
        name='email-notify-%s-%s' % (
            models.human_hash(email_address), sequence_number),
        countdown=countdown)
    task_list.append(task)

  logging.debug('Enqueuing email notification tasks for %d users',
                len(task_list))
  try:
    taskqueue.Queue(config.email_digest_queue).add(task_list)
  except (taskqueue.TombstonedTaskError, taskqueue.TaskAlreadyExistsError):
    logging.debug('Enqueued email tasks for emails=%r; '
                  'at least one task already present', emails_set)


class EmailDigestWorker(base.BaseHandler):
  """Sends email digests of shard activities to users."""

  @staticmethod
  @ndb.tasklet
  def get_topic_info(root_shard_id, email_address):
    """Gets detail about topics for a root shard, updates read state.

    Args:
      root_shard_id: Shard ID to list topics for.
      email_address: Address of the user whose read state should be updated
        after getting info.

    Returns:
      List of dictionaries, one for each topic, suitable for rendering
      email digest updates.
    """
    user_id = '%s:%s' % (root_shard_id, email_address)
    _, shard_and_state_list = yield list_topics(
        root_shard_id, user_id)

    topic_list = []
    update_dict = {}
    for topic_shard, read_state in shard_and_state_list:
      start_sequence = 1
      end_sequence = topic_shard.sequence_number
      if read_state:
        start_sequence = read_state.last_read_sequence

      updates_count = end_sequence - start_sequence
      if updates_count <= 0:
        # Nothing new with this topic, so leave it out of the digest.
        continue

      # TODO(bslatkin): Restrict the updated topics to just new topics?

      # TODO(bslatkin): Fetch all of the new posts for this topic and extract
      # the nicknames and/or gravatars of the users who have contributed.

      info = dict(
          topic_id=topic_shard.shard_id,
          last_update_time=topic_shard.update_time,
          title=topic_shard.title,
          description=topic_shard.description,
          creation_nickname=topic_shard.creation_nickname,
          start_sequence=start_sequence,
          end_sequence=end_sequence,
          updates_count=updates_count)

      topic_list.append(info)
      update_dict[topic_shard.shard_id] = end_sequence

    # TODO(bslatkin): Split this flow into two parts: One to generate the
    # parameters and save them somewhere, another to actually update the
    # read state. We'd want to do this to make sure that if errors happen
    # we will still always send email, but we don't risk sending the same
    # email twice. Right now we risk never sending an email at all.
    if update_dict:
      txn = lambda: update_read_state(update_dict, user_id)
      yield ndb.transaction_async(txn)

    raise ndb.Return(topic_list)

  def post(self):
    sequence_number = self.get_required('sequence_number', int)
    email_address = self.get_required('email_address', str)

    email_record = models.EmailRecord.get_or_insert(
        email_address,
        secret=models.human_uuid())

    if email_record.global_opt_out:
      logging.debug('Not sending email to globally opted out address=%r',
                    email_address)
      return

    if email_record.sequence_number > sequence_number:
      logging.warning(
          'Saw email digest task for address=%r, sequence_number=%r but '
          'email record already at sequence_number=%r; dropping task',
          email_address, sequence_number, email_record.sequence_number)
      return

    # Find all shards the user participates in with this email address.
    query = models.LoginRecord.query()
    query = query.filter(models.LoginRecord.email_address == email_address)
    login_record_list = query.fetch(1000)
    shard_set = set(u.shard_id for u in login_record_list)

    # Generate the template rendering params for each shard and all of its
    # topics based on the email's read state for each topic. Do this in
    # parallel since none of them are interdependent.
    futures_dict = {}
    for root_shard_id in shard_set:
      futures_dict[root_shard_id] = EmailDigestWorker.get_topic_info(
          root_shard_id, email_address)
    ndb.Future.wait_all(futures_dict.values())

    param_dict = {}
    for root_shard_id, future in futures_dict.iteritems():
      topic_info_list = future.get_result()
      if not topic_info_list:
        logging.debug('No updates for shard=%r, email=%r',
                      root_shard_id, email_address)
        continue

      param_dict[root_shard_id] = topic_info_list

    # Mark the email as having been processed so we can send future digests.
    def txn():
      email_record = models.EmailRecord.get_by_id(email_address)
      email_record.sequence_number = sequence_number + 1
      email_record.last_notified_time = datetime.datetime.now()
      email_record.put()
      return email_record

    email_record = ndb.transaction(txn)

    if not param_dict:
      logging.debug('No topics to digest for %s', email_address)
      return

    # Render the email content and send the email. We do this last so if
    # there are any bugs in the rendering code or sending step that it does
    # not result in us repeatedly sending emails to users. The transaction
    # above acts as a guard on this task.
    context = dict(email_record=email_record,
                   shards=param_dict)
    text_data = template.render('templates/digest_email.txt', context)
    html_data = template.render('templates/digest_email.html', context)
    sender = '8-bits of ephemera <notify@8-bits.us>'
    # TODO(bslatkin): Put how many new posts there are in the subject line.
    subject = 'Digest of new topics'

    logging.debug('Sending email digest to=%r, sender=%r, subject=%r',
                  email_address, sender, subject)
    logging.debug('Text:\n%s', text_data)
    logging.debug('HTML:\n%s', html_data)
    message = mail.EmailMessage(
        sender=sender,
        to=email_address,
        subject=subject,
        body=text_data,
        html=html_data)
    message.send()


ROUTES = [
  (r'/work/email_digest', EmailDigestWorker),
]
