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
goog.require('goog.string');
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
  this.logger_ = goog.debug.Logger.getLogger(
      'bits.connection.Connection:' + shardId);

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

  /**
   * @type {number}
   * @private
   */
  this.numErrors_ = 0;

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
    if (this.reportError_('Could not set presence', true)) {
      this.setPresence_();
    }
    return;
  }

  var response = event.target.getResponseJson();
  // TODO(bslatkin): Better validation of the response payload.

  // This is a reconnection after the user has been disconnected for a
  // while. This could be a page reload or a first time load. Send an event so
  // other components can take appropriate action, such as clearing out old
  // posts since they're out of date.
  var firstRequest = !this.browserToken_ || response.userConnected;
  if (firstRequest) {
    bits.events.PubSub.publish(
        this.shardId_, bits.events.EventType.ConnectionReestablishing);
  }

  // The browser token will be refreshed periodically, in addition to being
  // issued on the first presence request and relogin presence requests.
  if (this.browserToken_ != response.browserToken || firstRequest) {
    if (this.channel_) {
      if (this.channel_.close) {
        this.channel_.close();
      }
      this.channel_ = null;
    }

    this.browserToken_ = response.browserToken;
    this.allocateChannel_(firstRequest);
  }

  // Reset the error counter. If we can heartbeat, then we're in good shape.
  this.numErrors_ = 0;

  // Starting this timer repeatedly has no effect, but we don't want to
  // start it until we know the very first presence request was successful.
  this.heartbeatTimer_.start();
};


/**
 * Allocates a new channel with the current browser token.
 * @param {boolean} connected User was just connected for the first time in
 *   a while and some initial setup actions should be taken.
 * @private
 */
bits.connection.Connection.prototype.allocateChannel_ = function(connected) {
  this.channel_ = new goog.appengine.Channel(this.browserToken_);
  var socket = this.channel_.open({
    'onopen': goog.bind(this.handleChannelOpen_, this, connected),
    'onmessage': goog.bind(this.handleChannelMessage_, this),
    'onerror': goog.bind(this.handleChannelError_, this),
    'onclose': goog.bind(this.handleChannelClose_, this)
  });
};


/**
 * Handles when the channel opens.
 * @param {boolean} userConnected True if the user has just reconnected for
 *   the first time or is relogging in, False if this is just a token refresh.
 * @private
 */
bits.connection.Connection.prototype.handleChannelOpen_ =
    function(userConnected) {
  this.logger_.info('Connection now open');

  // Only refresh the roster upon new connections. When the roster becomes an
  // actual UI widget, then we can issue this request every time.
  if (userConnected) {
    this.requestOldPosts_();
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
  this.logger_.info('Connection heartbeat');
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
  this.logger_.info('Received message: ' + rawMessage);

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
    this.logger_.debug('Unknown message type: ' + rawMessage);
  }
};


/**
 * Handles when errors happen on the channel.
 * @param {object} event App Engine channel error object.
 * @private
 */
bits.connection.Connection.prototype.handleChannelError_ = function(event) {
  var retry = this.reportError_(
      'Could not establish channel: code=' + event['code'] +
      ', description=' + event['description'], true);
  if (retry) {
    // Reallocate the channel on errors, per
    //   http://stackoverflow.com/questions/10729842
    this.allocateChannel_(false);
  }
};


/**
 * Handles when the channel closes.
 * @param {object} event App Engine channel event object.
 * @private
 */
bits.connection.Connection.prototype.handleChannelClose_ = function(event) {
  this.logger_.info('Connection closed');
};


/**
 * Handles when the sending an RPC has an error.
 *
 * This logs detailed information about the Xhr. It's still up to functions
 * that make Xhrs to properly do retries and calls to reportError_.
 *
 * @param {object} event XHR error event.
 * @private
 */
bits.connection.Connection.prototype.handleSendError_ = function(event) {
  this.logger_.severe('Could not send message to handler: ' +
                      event.xhrIo.getLastUri());
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
  this.logger_.info('Submitting presence change');
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

  // Simulate the HTML escaping the server side would have done.
  postMap['nickname'] = goog.string.htmlEscape(postMap['nickname']);
  postMap['body'] = goog.string.htmlEscape(postMap['body']);

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
  if (!event.target.isSuccess()) {
    this.reportError_('Could not send post', true)
    return;
  }

  var responseJson = event.target.getResponseJson();
  this.logger_.info('Post submitted successfully: postId=' +
                    responseJson['postId']);
  bits.events.PubSub.publish(
      this.shardId_, bits.events.EventType.SubmittedPostReceived, postMap);
};


/**
 * Report an error to the user.
 *
 * @param {string} message Error message to show
 * @param {boolean=} opt_ignorable When true, it means the error message can
 *   be ignored and the caller will retry. If false, then this connection
 *   should be destroyed immediately.
 * @return {boolean} True if the caller can retry, regardless of whether or
 *   not it was ignorable. Callers should not retry if this returns false.
 */
bits.connection.Connection.prototype.reportError_ =
    function(message, opt_ignorable) {
  this.numErrors_++;
  var fatal = this.numErrors_ > 5 || !opt_ignorable;
  this.logger_.severe(message + ', ignorable=' + !!opt_ignorable +
                      ', numErrors=' + this.numErrors_ + ', fatal=' + fatal);

  if (fatal) {
    // Show the user a link to reload this page.
    message +=
        '<br>Fatal error: ' +
        '<a href="javascript:window.location=window.location">' +
        'Click here to reload</a>';
  }

  var postMap = {
      'shardId': this.shardId_,
      'body': message,
      'postTimeMs': (new goog.date.DateTime()).getTime(),
      'archiveType': bits.posts.ArchiveType.ERROR,
      'postId': 'system-error-' + this.getNextMessageId_()
  };
  bits.events.PubSub.publish(
      this.shardId_, bits.events.EventType.ServerError, postMap);

  if (!fatal) {
    return true;
  }

  // Kill the event handler so nothing fires for this connection again.
  this.eh_.removeAll();

  // Kill the pubsub system so all new user actions do nothing.
  bits.events.PubSub.clear();

  return false;
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
  if (!event.target.isSuccess()) {
    if (this.reportError_('Could not get roster', true)) {
      this.requestRoster_();
    }
    return;
  }

  var responseJson = event.target.getResponseJson();
  this.logger_.info('Received roster: ' + responseJson['roster']);
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
  if (!event.target.isSuccess()) {
    this.reportError_('Could not request historical posts', true);
    return;
  }

  var responseJson = event.target.getResponseJson();
  this.logger_.info('Received historical posts: start=' + start + ', end=' +
                    end + ', count=' + count);
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
