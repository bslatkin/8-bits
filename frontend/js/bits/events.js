// Copyright 2010 Brett Slatkin, Nathan Naze
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * @fileoverview PubSub events for cross-component messaging.
 */

goog.provide('bits.events');
goog.provide('bits.events.EventType');
goog.provide('bits.events.PubSub');

goog.require('goog.array');
goog.require('goog.debug.ErrorHandler');
goog.require('goog.debug.Logger');
goog.require('goog.object');
goog.require('goog.pubsub.PubSub');


/**
 * @enum {string}
 */
bits.events.EventType = {
  // User submits a new Post that should be sent to the server side.
  // Args:
  //   JSON for bits.posts.Post instance without any IDs.
  SubmitPost: 'SubmitPost',

  // User-submitted post was sent to the server side.
  // Args:
  //   JSON for bits.post.Post instance with postId and nickname set, but
  //   sequenceId missing.
  SubmittedPostSent: 'SubmittedPostSent',

  // Post received from the server side.
  // Args:
  //   JSON for bits.posts.Post instance with postId and sequenceId both set.
  PostReceived: 'PostReceived',

  // User submits a change to their presence settings.
  // Args:
  //  nickname: New nickname for the user.
  //  acceptedTerms: User has accepted terms for the first time.
  //  soundEnabled: True if the user wants to hear sounds.
  SubmitPresenceChange: 'SubmitPresenceChange',

  // The last action resulted in a server-returned error message.
  ServerError: 'ServerError',

  // The connection or system wants to show the user some information, such
  // as the fact that their connection has been reestablished after errors.
  SystemInfo: 'SystemInfo',

  // The user wants to see the settings dialog.
  // No arguments.
  ShowSettingsDialog: 'ShowSettingsDialog',

  // The user wants to see the short URL dialog.
  // No arguments.
  ShowShortUrlDialog: 'ShowShortUrlDialog',

  // The user wants to see the roster of users who are present.
  // No arguments.
  RequestRoster: 'RequestRoster',

  // The server has provided the roster of users who are present.
  // No arguments.
  RosterReceived: 'RosterReceived',

  // The user wants to see historical posts.
  //
  // If start and end are zero, then the most recent posts are fetched.
  //
  // Args:
  //   start: What post sequence number to start fetching. Inclusive.
  //   end: What post sequence number to stop fetching on. Inclusive.
  //   count: How many posts to retrieve.
  RequestHistoricalPosts: 'RequestHistoricalPosts',

  // Historical posts received from the server side.
  // Args:
  //   List of JSON for bits.posts.Post instances.
  HistoricalPostsReceived: 'HistoricalPostsReceived',

  // The user's connection to the server is being reestablished after a
  // very long time being offline.
  ConnectionReestablishing: 'ConnectionReestablishing',

  // User has submitted a URL for starting a new topic.
  // Args:
  //   link: URL that the user submitted.
  SubmitLink: 'SubmitLink',

  // User has submitted new topic.
  // Args:
  //   link: URL that the user submitted.
  //   summary: Text summary of the topic.
  SubmitTopic: 'SubmitTopic'
};


bits.events.PubSub.logger_ = null;


bits.events.PubSub.bridge_ = null;


bits.events.PubSub.setup = function() {
  if (!bits.events.PubSub.bridge_) {
    bits.events.PubSub.bridge_ = new goog.pubsub.PubSub();
  }
  if (!bits.events.PubSub.logger_) {
    bits.events.PubSub.logger_ =
        goog.debug.Logger.getLogger('bits.events.PubSub');
  }
};


/**
 * Clear all pubsub event handlers that are registered globally.
 */
bits.events.PubSub.clear = function() {
  bits.events.PubSub.setup();

  bits.events.PubSub.bridge_.clear();
};


bits.events.PubSub.getRealTopic_ = function(shardId, eventType) {
  return '' + shardId + '-' + eventType;
};


/**
 * Publishes a message.
 * @param {string} shardId ID of the shard to publish the message on.
 * @param {bits.events.EventType} eventType Type of event to publish.
 * @param {...*} var_args Arguments to publish in the message.
 */
bits.events.PubSub.publish = function(shardId, eventType, var_args) {
  bits.events.PubSub.setup();

  if (!goog.object.containsKey(bits.events.EventType, eventType)) {
    bits.events.PubSub.logger_.severe(
        'Invalid publish event type: ' + eventType);
    return;
  }
  var topic = bits.events.PubSub.getRealTopic_(shardId, eventType);
  var args = goog.array.slice(arguments, 2);
  args.unshift(topic);
  bits.events.PubSub.logger_.info(
      'Publish event: eventType=' + eventType + ', shardId=' + shardId);
  bits.events.PubSub.bridge_.publish.apply(bits.events.PubSub.bridge_, args);
};

/**
 * Subscribes to event messages.
 * @param {string} shardId ID of the shard to receive messages for.
 * @param {bits.events.EventType} eventType Type of event to receive.
 * @param {Function} fn Callback function to invoke on new events.
 * @param {Object=} opt_context Context to pass to the callback.
 */
bits.events.PubSub.subscribe = function(shardId, eventType, fn, opt_context) {
  bits.events.PubSub.setup();

  if (!goog.object.containsKey(bits.events.EventType, eventType)) {
    bits.events.PubSub.logger_.severe(
        'Invalid subscribe event type: ' + eventType);
    return;
  }
  var topic = bits.events.PubSub.getRealTopic_(shardId, eventType);
  bits.events.PubSub.bridge_.subscribe(topic, fn, opt_context);
};
