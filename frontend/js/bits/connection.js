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
goog.require('goog.Timer');
goog.require('goog.Uri');

goog.require('bits.events');

/**
 * Creates a new connection.
 *
 * @param {string} shardId Shard ID for this connection.
 * @param {string} nickname Initial nickname this user has.
 * @constructor
 */
bits.connection.Connection = function(shardId, nickname) {
  /**
   * @type {goog.debug.Logger}
   * @private
   */
  this.logger_ = goog.debug.Logger.getLogger('bits.connection.Connection');

  /**
   * Event handler for this object.
   * @type {goog.events.EventHandler}
   * @private
   */
  this.eh_ = new goog.events.EventHandler(this);

  /**
   * @type {goog.net.XhrManager}
   * @private
   */
  this.xhrManager_ = new goog.net.XhrManager();

  this.eh_.listen(
      this.xhrManager_, goog.net.EventType.ERROR, this.handleSendError_);
  this.eh_.listen(
      this.xhrManager_, goog.net.EventType.TIMEOUT, this.handleSendError_);

  /**
   * Timer used for heartbeat signals.
   * @type {goog.Timer}
   * @private
   */
  this.heartbeatTimer_ = new goog.Timer(60000);

  this.eh_.listen(
      this.heartbeatTimer_, goog.Timer.TICK, this.handleHeartbeat_);

  /**
   * @type {string}
   * @private
   */
  this.shardId_ = shardId;

  /**
   * @type {string}
   * @private
   */
  this.nickname_ = nickname;

  /**
   * The browser token currently being used for the channel.
   * @type {string}
   * @private
   */
  this.browserToken_ = null;

  /**
   * This is an external object goog.appengine.Channel.
   * TODO(bslatkin): Make this work with the closure compiler.
   *
   * @type {object?}
   */
  this.channel_ = null;

  /**
   * Used for XML RPC numbers and system messages.
   *
   * @type {number}
   * @private
   */
  this.nextMessageId_ = 0;

  // Subscribe to messages generated by the UI.
  bits.events.PubSub.subscribe(
      this.shardId_, bits.events.EventType.SubmitPost,
      this.handleSubmitPost_, this);
  bits.events.PubSub.subscribe(
      this.shardId_, bits.events.EventType.SubmitPresenceChange,
      this.handleSubmitPresenceChange_, this);
  bits.events.PubSub.subscribe(
      this.shardId_, bits.events.EventType.RequestRoster,
      this.requestRoster_, this);
  bits.events.PubSub.subscribe(
      this.shardId_, bits.events.EventType.RequestHistoricalPosts,
      this.requestOldPosts_, this);

};


/**
 * Login this connection.
 */
bits.connection.Connection.prototype.login = function() {
  this.setPresence_();
};


/**
 * Update presence for this connection.
 * @param {boolean=} opt_acceptedTerms User has just accepted the terms.
 * @private
 */
bits.connection.Connection.prototype.setPresence_ =
    function(opt_acceptedTerms) {
  var params = new goog.Uri.QueryData();
  params.add('shard', this.shardId_);
  params.add('nickname', this.nickname_);
  if (opt_acceptedTerms) {
    params.add('accepted_terms', 'true');
  }
  this.xhrManager_.send(
      this.getNextMessageId_(),
      '/rpc/presence',
      opt_method='POST',
      opt_content=params.toString(),
      null,
      null,
      goog.bind(this.handleSetPresenceComplete_, this));
};


/**
 * Handles when setPresence_ completes.
 * @param {goog.events.Event} event XHR response event.
 * @private
 */
bits.connection.Connection.prototype.handleSetPresenceComplete_ =
    function(event) {
  if (!event.target.isSuccess()) {
    // TODO(bslatkin): Retry RPC and eventually show error message.
    this.logger_.severe('Presence RPC failed');
    return;
  }

  var response = event.target.getResponseJson();
  if (!response.browserToken) {
    // TODO(bslatkin): Render an error.
    this.logger_.severe('Could not find browser token!');
    return;
  }

  // This is a reconnection after the user has been disconnected for a
  // while. Send an event so other components can take appropriate action,
  // such as clearing out old posts since they're out of date.
  var firstRequest = !this.browserToken_;
  if (response.userConnected && !firstRequest) {
    bits.events.PubSub.publish(
        this.shardId_, bits.events.EventType.ConnectionReestablishing);
  }

  // The browser token will be refreshed periodically, in addition to being
  // issued on the first presence request and relogin presence requests.
  if (this.browserToken_ != response.browserToken || response.userConnected) {
    if (this.channel_) {
      // TODO(bslatkin): This doesn't work locally: this.channel_.close();
      this.channel_ = null;
    }

    this.browserToken_ = response.browserToken;
    this.channel_ = new goog.appengine.Channel(this.browserToken_);
    var socket = this.channel_.open({
      'onopen': goog.bind(this.handleChannelOpen_, this,
                          response.userConnected),
      'onmessage': goog.bind(this.handleChannelMessage_, this),
      'onerror': goog.bind(this.handleChannelError_, this),
      'onclose': goog.bind(this.handleChannelClose_, this)
    });
  }

  // Starting this timer repeatedly has no effect, but we don't want to
  // start it until we know the very first presence request was successful.
  this.heartbeatTimer_.start();
};


/**
 * Handles when the channel opens.
 * @param {boolean} userConnected True if the user has just reconnected for
 *   the first time or is relogging in, False if this is just a token refresh.
 * @private
 */
bits.connection.Connection.prototype.handleChannelOpen_ =
    function(userConnected) {
  // TODO(bslatkin): Don't let the user start chatting until this is open.
  this.logger_.info('Connection to shardId=' + this.shardId_ + ' now open.');
  this.requestOldPosts_();

  // Only refresh the roster upon new connections. When the roster becomes an
  // actual UI widget, then we can issue this request every time.
  if (userConnected) {
    this.requestRoster_();
  }
};


/**
 * Handles the periodic heartbeat timer, to keep this connection alive.
 *
 * Notably, this timer will go off when a computer wakes up from sleep,
 * causing the connection to be reinitialized if it's been too long.
 *
 * @private
 */
bits.connection.Connection.prototype.handleHeartbeat_ = function() {
  this.logger_.info('Connection heartbeat for shardId=' + this.shardId_);
  this.setPresence_();
};


/**
 * Handles when a message is received on the channel.
 * @param {object} event App Engine channel event object.
 * @private
 */
bits.connection.Connection.prototype.handleChannelMessage_ = function(event) {
  var rawMessage = event['data'];
  var message = goog.json.parse(rawMessage);
  this.logger_.info('Received message for shardId=' + this.shardId_ + ': ' +
                    rawMessage);

  // Handle the different message types and translate them into pubsub messages.
  if (goog.object.containsKey(message, 'posts')) {
    var postList = message['posts'];
    // Sort Posts in ascending sequence order, oldest to newest.
    goog.array.sort(postList, function(a, b) {
      return a['sequenceId'] - b['sequenceId'];
    });
    goog.array.forEach(postList, function(postMap) {
      bits.events.PubSub.publish(
            this.shardId_, bits.events.EventType.PostReceived, postMap);
    }, this);
  } else {
    this.logger_.severe('Unknown message type: ' + rawMessage);
  }
};


/**
 * Handles when errors happen on the channel.
 * @param {object} event App Engine channel error object.
 * @private
 */
bits.connection.Connection.prototype.handleChannelError_ = function(event) {
  this.logger_.severe('Channel error for shardId=' + this.shardId_ + ':' +
                     event['data']);
  // TODO(bslatkin): Show the error to the user.
};


/**
 * Handles when the channel closes.
 * @param {object} event App Engine channel event object.
 * @private
 */
bits.connection.Connection.prototype.handleChannelClose_ = function(event) {
  this.logger_.info('Connection to shardId=' + this.shardId_ + ' closed.');
};


/**
 * Handles when the sending an RPC has an error.
 * @param {object} event App Engine channel event object.
 * @private
 */
bits.connection.Connection.prototype.handleSendError_ = function(event) {
  this.logger_.severe('Send error for shardId=' + this.shardId_ + ':' +
                     event['data']);
  // TODO(bslatkin): Show errors to the user.
};


/**
 * Gets the next unique message ID and increments it.
 * @return {number} Next unique message ID.
 */
bits.connection.Connection.prototype.getNextMessageId_ = function() {
  var messageId = this.nextMessageId_;
  this.nextMessageId_++;
  return messageId;
};


/**
 * Handles bits.events.EventType.SubmitPresenceChange requests.
 * @param {string} nickname New nickname for the user.
 * @param {boolean} acceptedTerms User has just accepted the terms of service.
 * @private
 */
bits.connection.Connection.prototype.handleSubmitPresenceChange_ =
    function(nickname, acceptedTerms) {
  this.logger_.info('Connection presence change for shardId=' + this.shardId_);
  this.nickname_ = nickname;
  this.setPresence_(acceptedTerms);
};


/**
 * Handles the bits.events.EventType.SubmitPost event.
 * @param {object} postMap JSON representation of a post.
 * @private
 */
bits.connection.Connection.prototype.handleSubmitPost_ = function(postMap) {
  // Update post's attributes to match connection's attributes.
  postMap['shardId'] = this.shardId_;
  postMap['postId'] = bits.connection.Connection.uuidCompact();
  postMap['nickname'] = this.nickname_;
  postMap['postTimeMs'] = (new goog.date.DateTime()).getTime();

  var params = new goog.Uri.QueryData();
  params.add('body', postMap['body']);
  params.add('post_id', postMap['postId']);
  params.add('type', postMap['archiveType']);
  params.add('shard', this.shardId_);
  this.xhrManager_.send(
      this.getNextMessageId_(),
      '/rpc/post',
      opt_method='POST',
      opt_content=params.toString(),
      null,
      null,
      goog.bind(this.handleSubmitPostSuccessful_, this, postMap));

  bits.events.PubSub.publish(
      this.shardId_, bits.events.EventType.SubmittedPostSent, postMap);
};

/**
 * Handles when a post is successfully submitted.
 * @param {object} postMap JSON representation of a post.
 * @param {goog.events.Event} event XHR event.
 * @private
 */
bits.connection.Connection.prototype.handleSubmitPostSuccessful_ =
    function(postMap, event) {
  var responseJson = event.target.getResponseJson();
  this.logger_.info('Post submitted successfully. ' +
                    'shardId="' + this.shardId_ + '", postId="' +
                    responseJson['postId'] + '"');
  bits.events.PubSub.publish(
      this.shardId_, bits.events.EventType.SubmittedPostReceived, postMap);
};


/**
 * Handles the bits.events.EventType.RequestRoster event.
 * @private
 */
bits.connection.Connection.prototype.requestRoster_ = function() {
  var params = new goog.Uri.QueryData();
  params.add('shard', this.shardId_);
  this.xhrManager_.send(
      this.getNextMessageId_(),
      '/rpc/show_roster',
      opt_method='POST',
      opt_content=params.toString(),
      null,
      null,
      goog.bind(this.handleRequestRosterSuccessful_, this));
};


/**
 * Handles when requesting the roster was succcessful.
 * @param {goog.events.Event} event XHR request event.
 * @private
 */
bits.connection.Connection.prototype.handleRequestRosterSuccessful_ =
    function(event) {
  var responseJson = event.target.getResponseJson();
  this.logger_.info('Received roster for shardId="' + this.shardId_ +
                    '", roster="' + responseJson['roster'] + '"');
  var postMap = {
      'shardId': this.shardId_,
      'body': responseJson['roster'],
      'postTimeMs': (new goog.date.DateTime()).getTime(),
      'archiveType': bits.posts.ArchiveType.ROSTER,
      'postId': 'system-message-' + this.getNextMessageId_()
  };
  bits.events.PubSub.publish(
      this.shardId_, bits.events.EventType.RosterReceived, postMap);
};


/**
 * Handles the bits.events.EventType.RequestHistoricalPosts event.
 * @param {number=} opt_start What post to start requesting. Inclusive.
 * @param {number=} opt_end What post to end requesting. Inclusive.
 * @param {number=} opt_count How many posts to fetch.
 * @private
 */
bits.connection.Connection.prototype.requestOldPosts_ =
    function(opt_start, opt_end, opt_count) {
  // TODO(bslatkin): Add a guard so only one of these is outstanding.
  var params = new goog.Uri.QueryData();
  var start = opt_start || 0;
  var end = opt_end || 0;
  var count = opt_count || 100;
  params.add('shard', this.shardId_);
  params.add('start', start);
  params.add('end', end);
  params.add('count', count);
  this.xhrManager_.send(
      this.getNextMessageId_(),
      '/rpc/list_posts',
      opt_method='POST',
      opt_content=params.toString(),
      null,
      null,
      goog.bind(this.handleRequestHistoricalPostsSuccessful_, this,
                start, end, count));
};


/**
 * Handles when requesting historical posts is successful.
 * @param {number} start Start value passed to requestOldPosts.
 * @param {number} end End value passed to requestOldPosts.
 * @param {number} count Count value passed to requestOldPosts.
 * @param {goog.events.Event} event XHR request event.
 */
bits.connection.Connection.prototype.handleRequestHistoricalPostsSuccessful_ =
    function(start, end, count, event) {
  var responseJson = event.target.getResponseJson();
  this.logger_.info('Received historical posts for shardId="' + this.shardId_ +
                    '", start="' + start + '", end="' + end +
                    '", count="' + count + '"');
  bits.events.PubSub.publish(
      this.shardId_,
      bits.events.EventType.HistoricalPostsReceived,
      responseJson['posts']);
};


/**
 * Generates a UUID.
 *
 * From MIT-licensed code at http://www.broofa.com/Tools/Math.uuid.js
 *
 * @return {string} UUID in hex.
 */
bits.connection.Connection.uuidCompact = function() {
  return 'xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
    var r = Math.random()*16|0, v = c == 'x' ? r : (r&0x3|0x8);
    return v.toString(16);
  });
};
