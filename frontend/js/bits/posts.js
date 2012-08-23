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
 * @fileoverview Represents posts and a container of posts.
 */

goog.provide('bits.posts.ArchiveType');
goog.provide('bits.posts.Post');
goog.provide('bits.posts.PostContainer');

goog.require('goog.array');
goog.require('goog.asserts');
goog.require('goog.date');
goog.require('goog.date.DateTime');
goog.require('goog.debug.Logger');
goog.require('goog.dom');
goog.require('goog.dom.classes');
goog.require('goog.events');
goog.require('goog.events.EventHandler');
goog.require('goog.events.EventType');
goog.require('goog.pubsub.PubSub');
goog.require('goog.structs.Map');
goog.require('goog.ui.Container');
goog.require('goog.ui.ContainerScroller');
goog.require('goog.ui.Control');
goog.require('goog.ui.Tooltip');
goog.require('goog.userAgent');

goog.require('bits.events');
goog.require('bits.ui.Scrollbar');


/**
 * Must stay in sync with Python models.Post.ARCHIVE_TYPES
 *
 * @enum {string}
 */
bits.posts.ArchiveType = {
  CHAT: 'chat',
  INFO: 'info',
  ERROR: 'error',
  ROSTER: 'roster',
  TOPIC_START: 'topic_start',
  TOPIC_CHANGE: 'topic_change',
  UNKNOWN: 'unknown',
  USER_LOGIN: 'user_login',
  USER_LOGOUT: 'user_logout',
  USER_UPDATE: 'user_update'
};


/**
 * A post to display.
 *
 * @param {object} postMap the map of post attributes.
 * @extends {goog.ui.Control}
 * @constructor
 */
bits.posts.Post = function(postMap) {
  goog.base(this);

  /**
   * @type {string}
   */
  this.shardId = postMap.shardId || null;

  /**
   * @type {bits.posts.ArchiveType}
   */
  this.archiveType = postMap.archiveType || bits.posts.ArchiveType.UNKNOWN;

  /**
   * @type {string}
   */
  this.nickname = postMap.nickname || null;

  /**
   * @type {string}
   */
  this.body = postMap.body || null;

  /**
   * @type {number?}
   */
  this.postTimeMs = postMap.postTimeMs || null;

  /**
   * @type {goog.date.DateTime}
   */
  this.postDateTime = null;
  if (this.postTimeMs) {
    this.postDateTime = new goog.date.DateTime();
    this.postDateTime.setTime(this.postTimeMs);
  }

  /**
   * @type {string}
   */
  this.postId = postMap.postId || null;

  /**
   * @type {string}
   */
  this.sequenceId = postMap.sequenceId || null;

  /**
   * @type {string}
   */
  this.postAttachment = postMap.postAttachment || null;
};
goog.inherits(bits.posts.Post, goog.ui.Control);


/**
 * Creates an initial DOM representation for the component.
 */
bits.posts.Post.prototype.createDom = function() {
  var element = this.dom_.createElement('div');
  goog.dom.classes.add(element, goog.getCssName('bits-post'));

  switch (this.archiveType) {
    case bits.posts.ArchiveType.CHAT:
      this.renderChat(element);
      break;

    case bits.posts.ArchiveType.USER_LOGIN:
    case bits.posts.ArchiveType.USER_LOGOUT:
    case bits.posts.ArchiveType.USER_UPDATE:
    case bits.posts.ArchiveType.ROSTER:
      this.renderPresence(element);
      break;

    case bits.posts.ArchiveType.INFO:
      this.renderInfo(element);
      break;

    case bits.posts.ArchiveType.ERROR:
      this.renderError(element);
      break;

    default:
      break;
  }

  var tooltip = new goog.ui.Tooltip(
      element,
      'Posted at ' + this.postDateTime.toUsTimeString() + ', ' +
      (this.postDateTime.getMonth() + 1) + '/' +
      this.postDateTime.getDate() + '/' +
      this.postDateTime.getFullYear(),
      this.dom_);
  tooltip.className = 'bits-post-tooltip';
  this.decorateInternal(element);
};


/**
 * Render a chat message as a post.
 * @param {Element} element HTML element to decorate.
 */
bits.posts.Post.prototype.renderChat = function(element) {
  goog.dom.classes.add(element, goog.getCssName('bits-post-chat'));

  var nicknameDiv = this.dom_.createElement('span');
  goog.dom.classes.add(nicknameDiv, goog.getCssName('bits-post-chat-nickname'));
  nicknameDiv.innerHTML = this.nickname;

  var separatorDiv = this.dom_.createElement('span');
  goog.dom.classes.add(separatorDiv,
                       goog.getCssName('bits-post-chat-separator'));
  this.dom_.setTextContent(separatorDiv, ': ');

  var bodyDiv = this.dom_.createElement('span');
  goog.dom.classes.add(bodyDiv, goog.getCssName('bits-post-chat-body'));

  // Apply filters to linkify it safely. The regex means we're very open to
  // all kinds of crazy links here.
  var rewritten = this.body.replace(
      /(http(s?):\/\/[^ '"\)\(]+)/g,
      '<a href="$1" target="_blank" class="bits-chatroom-link">$1</a>');
  bodyDiv.innerHTML = rewritten;

  element.appendChild(nicknameDiv);
  element.appendChild(separatorDiv);
  element.appendChild(bodyDiv);
};


/**
 * Render a presence message as a post.
 * @param {Element} element HTML element to decorate.
 */
bits.posts.Post.prototype.renderPresence = function(element) {
  goog.dom.classes.add(element, goog.getCssName('bits-post-presence'));

  var bodyDiv = this.dom_.createElement('span');
  goog.dom.classes.add(bodyDiv, goog.getCssName('bits-post-presence-body'));
  bodyDiv.innerHTML = this.body;

  element.appendChild(bodyDiv);
};


/**
 * Render an info message as a post.
 * @param {Element} element HTML element to decorate.
 */
bits.posts.Post.prototype.renderInfo = function(element) {
  goog.dom.classes.add(element, 'bits-post-info');

  var bodyDiv = this.dom_.createDom('span', 'bits-post-info-body');
  bodyDiv.innerHTML = this.body;

  element.appendChild(bodyDiv);
};


/**
 * Render an error message as a post.
 * @param {Element} element HTML element to decorate.
 */
bits.posts.Post.prototype.renderError = function(element) {
  goog.dom.classes.add(element, goog.getCssName('bits-post-error'));

  var bodyDiv = this.dom_.createElement('span');
  goog.dom.classes.add(bodyDiv, goog.getCssName('bits-post-error-body'));
  bodyDiv.innerHTML = this.body;

  element.appendChild(bodyDiv);
};


/**
 * Decorates an existing HTML DIV element as a Post.
 *
 * @param {HTMLElement} element The DIV element to decorate.
 */
bits.posts.Post.prototype.decorateInternal = function(element) {
  bits.posts.Post.superClass_.decorateInternal.call(this, element);

  var elem = this.getElement();
  elem.tabIndex = 0;
  this.setAllowTextSelection(true);
};


/**
 * Disposes of the component.
 */
bits.posts.Post.prototype.disposeInternal = function() {
  bits.posts.Post.superClass_.disposeInternal.call(this);
};


/**
 * Called when component's element is known to be in the document.
 */
bits.posts.Post.prototype.enterDocument = function() {
  bits.posts.Post.superClass_.enterDocument.call(this);
};


/**
 * Called when component's element is known to have been removed from the
 * document.
 */
bits.posts.Post.prototype.exitDocument = function() {
  bits.posts.Post.superClass_.exitDocument.call(this);
};


/**
 * Contains multiple Post instances in a scrollable, self-populating view.
 *
 * @param {string} shardId ID of the shard this is for.
 * @extends {goog.ui.Component}
 * @constructor
 */
bits.posts.PostContainer = function(shardId) {
  goog.base(this);

  /**
   * @type {goog.debug.Logger}
   * @private
   */
  this.logger_ = goog.debug.Logger.getLogger(
      'bits.posts.PostContainer:' + shardId);

  /**
   * @type {string}
   */
  this.shardId = shardId;

  /**
   * Keep track of the list of Posts we have already seen. Keys are IDs
   * unique to each post but separate from the sequence numbers because
   * IDs have no ordering. When a user posts a message they will insert the
   * Post into their own PostContainer immediately after it's received by the
   * server side. Then when the post comes through over the channel the Post's
   * sequence number (thus far missing/unassigned) will be updated to match
   * the server's assignment.
   *
   * @type {goog.structs.Map}
   */
  this.postIdMap = new goog.structs.Map();

  /**
   * Lowest sequence number that is present in this container.
   * @type {number?}
   */
  this.lowestSequenceId = null;

  /**
   * @type {goog.events.EventHandler}
   * @private
   */
  this.eh_ = new goog.events.EventHandler(this);

  /**
   * @type {goog.ui.Container}
   */
  this.container = new goog.ui.Container();
  this.container.setFocusableChildrenAllowed(false);
  this.container.setFocusable(true);

  /**
   * @type {bits.ui.Scrollbar}
   */
  this.scrollbar_ = new bits.ui.Scrollbar();
}
goog.inherits(bits.posts.PostContainer, goog.ui.Component);


/**
 * Creates an initial DOM representation for the component.
 */
bits.posts.PostContainer.prototype.createDom = function() {
  // xxx
  this.decorateInternal(this.dom_.createDom('div', 'bits-post-container'));
};


/**
 * Decorates an existing HTML DIV element as a PostContainer.
 *
 * @param {HTMLElement} element The DIV element to decorate.
 */
bits.posts.PostContainer.prototype.decorateInternal = function(element) {
  bits.posts.PostContainer.superClass_.decorateInternal.call(this, element);

  var elem = this.getElement();

  // Make the list of posts scrollable.
  var containerEl = this.dom_.getElementByClass('bits-post-container', elem);
  this.container.decorate(containerEl);
  goog.style.setUnselectable(containerEl, false, goog.userAgent.GECKO);
  var containerScroller = new goog.ui.ContainerScroller(this.container);
  this.registerDisposable(containerScroller);

  // Put a scrollbar to the container.
  this.scrollbar_.setTarget(containerEl);
  this.scrollbar_.render(elem);
  this.registerDisposable(this.scrollbar_);
};


/**
 * Disposes of the component.
 */
bits.posts.PostContainer.prototype.disposeInternal = function() {
  bits.posts.PostContainer.superClass_.disposeInternal.call(this);
  this.eh_.dispose();
};


/**
 * Called when component's element is known to be in the document.
 */
bits.posts.PostContainer.prototype.enterDocument = function() {
  bits.posts.PostContainer.superClass_.enterDocument.call(this);

  this.eh_.listen(
      this.getElement(), goog.events.EventType.SCROLL, this.handleScroll_);

  // Subscribe to internal events.
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.PostReceived,
      this.handlePostReceived, this);
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.HistoricalPostsReceived,
      this.handleHistoricalPostsReceived, this);

  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.SubmittedPostSent,
      this.handlePostReceived, this);
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.SubmittedPostReceived,
      this.handlePostReceived, this);
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.RosterReceived,
      this.handlePostReceived, this);
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.ServerError,
      this.handlePostReceived, this);
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.SystemInfo,
      this.handlePostReceived, this);
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.ConnectionReestablishing,
      this.handleReestablishing_, this);
};


/**
 * Called when component's element is known to have been removed from the
 * document.
 */
bits.posts.PostContainer.prototype.exitDocument = function() {
  bits.posts.PostContainer.superClass_.exitDocument.call(this);
};


/**
 * Handles when a post is received and should be added to the container.
 * @param {object} postMap Post JSON object received from the server.
 */
bits.posts.PostContainer.prototype.handlePostReceived = function(postMap) {
  this.addOrUpdatePost(new bits.posts.Post(postMap));
};


/**
 * Handles when historical posts were received.
 * @param {Array.<object>} postMapList List of post JSON objects.
 */
bits.posts.PostContainer.prototype.handleHistoricalPostsReceived =
    function(postMapList) {
  var postList = [];
  for (var i = 0, n = postMapList.length; i < n; i++) {
    postList.push(new bits.posts.Post(postMapList[i]));
  }
  this.prependPosts(postList);
};


/**
 * Handles when the user has reconnected.
 */
bits.posts.PostContainer.prototype.handleReestablishing_ = function() {
  this.postIdMap.clear();
  this.container.removeChildren(true);
};


/**
 * Prepend posts to the container that came before existing posts.
 * @param {Array.<bits.posts.Post>} postList List of post objects.
 */
bits.posts.PostContainer.prototype.prependPosts = function(postList) {
  if (postList.length == 0) {
    return;
  }

  // Sort in descending sequence order, newest to oldest.
  goog.array.sort(postList, function(a, b) {
    return b.sequenceId - a.sequenceId;
  });

  // Update the oldest sequence number that we know of.
  if (goog.isNull(this.lowestSequenceId) ||
      postList[postList.length - 1].sequenceId < this.lowestSequenceId) {
    this.lowestSequenceId = postList[postList.length - 1].sequenceId;
  }

  // Insert the posts, newest to oldest.
  goog.array.forEach(postList, function(post) {
    if (!this.postIdMap.containsKey(post.postId)) {
      this.postIdMap.set(post.postId, post);

      var scrollHeightBefore = this.container.getElement().scrollHeight;
      this.container.addChildAt(post, 0, true);
      var scrollHeightAfter = this.container.getElement().scrollHeight;

      // Keep the scrollbar in the exact same position after a historical
      // post has been added. This doesn't work if the scrollbar wasn't
      // showing yet.
      this.container.getElement().scrollTop +=
          scrollHeightAfter - scrollHeightBefore;
    }
  }, this);
};


/**
 * Adds a post to the container or updates it in-place.
 * @param {bits.posts.Post} post Post to add or update.
 */
bits.posts.PostContainer.prototype.addOrUpdatePost = function(post) {
  var scrollAtBottom =
      this.container.getElement().scrollHeight ==
      (this.container.getElement().scrollTop +
       this.container.getElement().clientHeight);

  if (post.sequenceId &&
      this.lowestSequenceId &&
      post.sequenceId < this.lowestSequenceId) {
    // Keep track of the oldest post we've seen.
    this.lowestSequenceId = post.sequenceId;
  }

  var foundPost = this.postIdMap.get(post.postId);
  if (foundPost) {
    if (!foundPost.sequenceId && post.sequenceId) {
      // Assign the sequence number if this is a post-updating message.
      foundPost.sequenceId = post.sequenceId;
    }
    return;
  }

  this.postIdMap.set(post.postId, post);
  this.container.addChildAt(post, this.postIdMap.getCount() - 1, true);

  if (scrollAtBottom) {
    // When the scrollbar is at the bottom, continue to automatically
    // advance the document on new posts. When the scrollbar is anywhere else,
    // leave it be so the user can keep their state.
    this.container.getElement().scrollTop =
        this.container.getElement().scrollHeight -
        this.container.getElement().clientHeight;
  }
};


/**
 * Handles when the container is scrolled.
 * @param {goog.events.Event} event Event that was dispatched.
 */
bits.posts.PostContainer.prototype.handleScroll_ = function(event) {
  if (this.container.getElement().scrollHeight <
      this.container.getElement().clientHeight) {
    return;
  }
  if (this.container.getElement().scrollTop > 0) {
    return;
  }

  bits.events.PubSub.publish(
      this.shardId,
      bits.events.EventType.RequestHistoricalPosts,
      0,
      this.lowestSequenceId || 0);
};
