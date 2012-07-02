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
goog.require('goog.debug.Logger');
goog.require('goog.object');
goog.require('goog.pubsub.PubSub');


bits.events.EventType = {
  // User submits a new Post that should be sent to the server side.
  // Args:
  //   JSON for bits.posts.Post instance with keys sequenceId and
  //   nickname unset, but postId already set to a valid UUID.
  SubmitPost: 'SubmitPost',

  // User-submitted post was sent to the server side.
  // Args:
  //   JSON for bits.post.Post instance with postId and nickname set, but
  SubmittedPostSent: 'SubmittedPostSent',

  // User-submitted post was received by the server side.
  // Args:
  //   JSON for bits.posts.Post instance with postId set and sequenceId missing.
  SubmittedPostReceived: 'SubmittedPostReceived',

  // Post received from the server side.
  // Args:
  //   JSON for bits.posts.Post instance with postId and sequenceId both set.
  PostReceived: 'PostReceived',

  // The last action resulted in a server-returned error.
  // Args:
  //   Originating bits.events.EventType that led to this server-returned error.
  //   Error class that occurred.
  //   Error message of the error.
  //   Traceback from the server-side error.
  ServerError: 'ServerError'
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
}


bits.events.PubSub.getRealTopic_ = function(shardId, eventType) {
  return '' + shardId + '-' + eventType;
}


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
      'Publish event: shardId=' + shardId + ', eventType=' + eventType);
  bits.events.PubSub.bridge_.publish.apply(bits.events.PubSub.bridge_, args);
}


bits.events.PubSub.subscribe = function(shardId, eventType, fn, opt_context) {
  bits.events.PubSub.setup();

  if (!goog.object.containsKey(bits.events.EventType, eventType)) {
    bits.events.PubSub.logger_.severe(
        'Invalid subscribe event type: ' + eventType);
    return;
  }
  var topic = bits.events.PubSub.getRealTopic_(shardId, eventType);
  bits.events.PubSub.bridge_.subscribe(topic, fn, opt_context);
}
