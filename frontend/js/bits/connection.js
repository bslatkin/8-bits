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
 * @fileoverview Represents an open connection for an 8-bits shard.
 */

goog.provide('bits.connection.Connection');

goog.require('goog.array');
goog.require('goog.debug.Logger');
goog.require('goog.events');
goog.require('goog.json');
goog.require('goog.net.EventType');
goog.require('goog.net.XhrManager');
goog.require('goog.object');
goog.require('goog.Uri');

goog.require('bits.events');


bits.connection.Connection = function(shardId, nickname) {
  this.logger_ = goog.debug.Logger.getLogger('bits.connection.Connection');
  this.shardId = shardId;
  this.nickname = nickname;

  this.xhrManager = new goog.net.XhrManager();

  goog.events.listen(
      this.xhrManager, goog.net.EventType.ERROR,
      goog.bind(this.handleSendError, this));

  goog.events.listen(
      this.xhrManager, goog.net.EventType.TIMEOUT,
      goog.bind(this.handleSendError, this));

  this.channel = null;
  this.nextMessageId = 0;

  // Subscribe to messages generated by the UI.
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.SubmitPost,
      goog.bind(this.handleSubmitPost, this));
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.SubmitPresenceChange,
      goog.bind(this.handleSubmitPresenceChange, this));
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.RequestRoster,
      goog.bind(this.requestRoster, this));
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.RequestHistoricalPosts,
      goog.bind(this.requestOldPosts, this));

};


bits.connection.Connection.prototype.login = function() {
  var params = new goog.Uri.QueryData();
  params.add('shard', this.shardId);
  params.add('mode', 'join');
  this.xhrManager.send(
    this.getNextMessageId(),
    '/rpc/login',
    opt_method='POST',
    opt_content=params.toString(),
    null,
    null,
    goog.bind(this.handleConnect, this));
};


bits.connection.Connection.prototype.handleConnect = function(event) {
  if (event.target.isSuccess()) {
    var response = event.target.getResponseJson();
    if (!response.browserToken) {
      this.logger_.severe('Could not find browser token!');
      return;
    }
    this.setPresence();
    this.requestRoster();
    this.requestOldPosts();

    this.channel = new goog.appengine.Channel(response.browserToken);
    var socket = this.channel.open({
      'onopen': goog.bind(this.handleChannelOpen, this),
      'onmessage': goog.bind(this.handleChannelMessage, this),
      'onerror': goog.bind(this.handleChannelError, this),
      'onclose': goog.bind(this.handleChannelClose, this)
    });
  } else {
    this.logger_.severe('Could not connect!');
  }
};


bits.connection.Connection.prototype.setPresence = function() {
  var params = new goog.Uri.QueryData();
  params.add('shard', this.shardId);
  params.add('nickname', this.nickname);
  this.xhrManager.send(
    this.getNextMessageId(),
    '/rpc/presence',
    opt_method='POST',
    opt_content=params.toString(),
    null,
    null,
    goog.bind(this.handleSetPresence, this));
};


bits.connection.Connection.prototype.handleSubmitPresenceChange =
    function(data) {
  this.nickname = data.nickname;
  this.setPresence();
};


bits.connection.Connection.prototype.handleSetPresence = function(event) {
  if (!event.target.isSuccess()) {
    this.logger_.severe('Could not set presence!');
  }
};


bits.connection.Connection.prototype.handleChannelOpen = function() {
  this.logger_.info('Connection to shardId=' + this.shardId + ' now open.');
  // TODO: Maybe handle errors here?
};


bits.connection.Connection.prototype.handleChannelMessage = function(event) {
  var message = goog.json.parse(event.data);
  this.logger_.info('Received message for shardId=' + this.shardId + ': ' +
                    event.data);

  // Handle the different message types and translate them into pubsub messages.
  if (goog.object.containsKey(message, 'posts')) {
    var postList = message.posts;
    // Sort Posts in ascending sequence order, oldest to newest.
    goog.array.sort(postList, function(a, b) {
      return a.sequenceId - b.sequenceId;
    });
    goog.array.forEach(postList, function(postMap) {
      bits.events.PubSub.publish(
            this.shardId, bits.events.EventType.PostReceived, postMap);
    }, this);
  } else {
    this.logger_.severe('Unknown message type: ' + event.data);
  }
};


bits.connection.Connection.prototype.handleChannelError = function(event) {
  this.logger_.severe('Channel error for shardId=' + this.shardId + ':' +
                     event.data);
};


bits.connection.Connection.prototype.handleChannelClose = function(event) {
  this.logger_.info('Connection to shardId=' + this.shardId + ' closed.');
};


bits.connection.Connection.prototype.handleSendError = function(event) {
  this.logger_.severe('Send error for shardId=' + this.shardId + ':' +
                     event.data);
};


bits.connection.Connection.prototype.getNextMessageId = function() {
  var messageId = this.nextMessageId;
  this.nextMessageId++;
  return messageId;
};


bits.connection.Connection.prototype.handleSubmitPost = function(postMap) {
  // Update post's attributes to match connection's attributes.
  postMap.shardId = this.shardId;
  postMap.postId = bits.connection.Connection.uuidCompact();
  postMap.nickname = this.nickname;
  postMap.postTimeMs = (new goog.date.DateTime()).getTime();

  var params = new goog.Uri.QueryData();
  params.add('body', postMap.body);
  params.add('post_id', postMap.postId);
  params.add('type', postMap.archiveType);
  params.add('shard', this.shardId);
  this.xhrManager.send(
    this.getNextMessageId(),
    '/rpc/post',
    opt_method='POST',
    opt_content=params.toString(),
    null,
    null,
    goog.bind(this.handleSubmitPostSuccessful, this, postMap));

  bits.events.PubSub.publish(
      this.shardId, bits.events.EventType.SubmittedPostSent, postMap);
};


bits.connection.Connection.prototype.handleSubmitPostSuccessful =
    function(postMap, event) {
  var responseJson = event.target.getResponseJson();
  this.logger_.info('Post submitted successfully. ' +
                    'shardId="' + this.shardId + '", postId="' +
                    responseJson.postId + '"');
  bits.events.PubSub.publish(
      this.shardId, bits.events.EventType.SubmittedPostReceived, postMap);
};


bits.connection.Connection.prototype.requestRoster = function() {
  var params = new goog.Uri.QueryData();
  params.add('shard', this.shardId);
  this.xhrManager.send(
    this.getNextMessageId(),
    '/rpc/show_roster',
    opt_method='POST',
    opt_content=params.toString(),
    null,
    null,
    goog.bind(this.handleRequestRosterSuccessful, this));
};


bits.connection.Connection.prototype.handleRequestRosterSuccessful =
    function(event) {
  var responseJson = event.target.getResponseJson();
  this.logger_.info('Received roster for shardId="' + this.shardId +
                    '", roster="' + responseJson.roster + '"');
  var postMap = {
    shardId: this.shardId,
    body: responseJson.roster,
    postTimeMs: (new goog.date.DateTime()).getTime(),
    archiveType: bits.posts.ArchiveType.ROSTER
  }
  bits.events.PubSub.publish(
      this.shardId, bits.events.EventType.RosterReceived, postMap);
};


bits.connection.Connection.prototype.requestOldPosts =
    function(start, end, count) {
  // TODO(bslatkin): Add a guard so only one of these is outstanding.
  var params = new goog.Uri.QueryData();
  start = start || 0;
  end = end || 0;
  count = count || 100;
  params.add('shard', this.shardId);
  params.add('start', start);
  params.add('end', end);
  params.add('count', count);
  this.xhrManager.send(
    this.getNextMessageId(),
    '/rpc/list_posts',
    opt_method='POST',
    opt_content=params.toString(),
    null,
    null,
    goog.bind(this.handleRequestHistoricalPostsSuccessful, this, start, end));
};


bits.connection.Connection.prototype.handleRequestHistoricalPostsSuccessful =
    function(start, end, event) {
  var responseJson = event.target.getResponseJson();
  this.logger_.info('Received historical posts for shardId="' + this.shardId +
                    '", start="' + start + '", end="' + end + '"');
  bits.events.PubSub.publish(
      this.shardId,
      bits.events.EventType.HistoricalPostsReceived,
      responseJson.posts);
};


/**
 * Generates a UUID.
 *
 * From MIT-licensed code at http://www.broofa.com/Tools/Math.uuid.js
 */
bits.connection.Connection.uuidCompact = function() {
  return 'xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    var r = Math.random()*16|0, v = c == 'x' ? r : (r&0x3|0x8);
    return v.toString(16);
  });
};
