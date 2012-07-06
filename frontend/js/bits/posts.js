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
 * @fileoverview Contains a set of views of posts, allowing for more posts
 *   to be looked up in the post history when the top of the scroll region
 *   has been accessed by the user.
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
goog.require('goog.events.KeyCodes');
goog.require('goog.events.KeyHandler');
goog.require('goog.events.KeyHandler.EventType');
goog.require('goog.pubsub.PubSub');
goog.require('goog.ui.Container');
goog.require('goog.ui.ContainerScroller');
goog.require('goog.ui.Control');
goog.require('goog.ui.Tooltip');
goog.require('goog.userAgent');
goog.require('goog.structs.Map');

goog.require('bits.events');


/* Must stay in sync with Python models.Post.ARCHIVE_TYPES */
bits.posts.ArchiveType = {
  CHAT: 'chat',
  NEWS: 'news',
  FILE: 'file',
  USER_LOGIN: 'user_login',
  USER_LOGOUT: 'user_logout',
  USER_UPDATE: 'user_update',
  ROSTER: 'roster',
  UNKNOWN: 'unknown'
};


/**
 * A post to display.
 *
 * @param {object} postMap the map of post attributes.
 * @param {goog.ui.ControlRenderer=} opt_renderer Renderer used to render.
 * @param {goog.dom.DomHelper=} opt_domHelper DOM helper to use.
 *
 * @extends {goog.ui.Component}
 * @constructor
 */
bits.posts.Post = function(postMap, opt_renderer, opt_domHelper) {
  goog.base(this, opt_renderer, opt_domHelper);

  this.shardId = postMap.shardId || null;
  this.archiveType = postMap.archiveType || bits.posts.ArchiveType.UNKNOWN;
  this.nickname = postMap.nickname || null;
  this.body = postMap.body || null;
  this.postTimeMs = postMap.postTimeMs || null;
  this.postDateTime = null;
  if (this.postTimeMs) {
    this.postDateTime = new goog.date.DateTime();
    this.postDateTime.setTime(this.postTimeMs);
  }
  this.postId = postMap.postId || null;
  this.sequenceId = postMap.sequenceId || null;
  this.postName = postMap.postName || null;
  this.postAttachment = postMap.postAttachment || null;

  /**
   * Event handler for this object.
   * @type {goog.events.EventHandler}
   * @private
   */
  this.eh_ = new goog.events.EventHandler(this);
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

    case bits.posts.ArchiveType.NEWS:
      break;

    case bits.posts.ArchiveType.FILE:
      break;

    case bits.posts.ArchiveType.USER_LOGIN:
    case bits.posts.ArchiveType.USER_LOGOUT:
    case bits.posts.ArchiveType.USER_UPDATE:
    case bits.posts.ArchiveType.ROSTER:
      this.renderPresence(element);
      break;

    default:
      break;
  }

  var tooltip = new goog.ui.Tooltip(
      element,
      'Received at ' + this.postDateTime.toUsTimeString() + ', ' +
      (this.postDateTime.getMonth() + 1) + '/' +
      this.postDateTime.getDate() + '/' +
      this.postDateTime.getFullYear(),
      this.dom_);
  tooltip.className = 'bits-post-tooltip';
  this.decorateInternal(element);
};


bits.posts.Post.prototype.renderChat = function(element) {
  // TODO(bslatkin): HTML escaping.
  goog.dom.classes.add(element, goog.getCssName('bits-post-chat'));

  var nicknameDiv = this.dom_.createElement('span');
  goog.dom.classes.add(nicknameDiv, goog.getCssName('bits-post-chat-nickname'));
  this.dom_.setTextContent(nicknameDiv, this.nickname);

  var separatorDiv = this.dom_.createElement('span');
  goog.dom.classes.add(separatorDiv,
                       goog.getCssName('bits-post-chat-separator'));
  this.dom_.setTextContent(separatorDiv, ': ');

  var bodyDiv = this.dom_.createElement('span');
  goog.dom.classes.add(bodyDiv, goog.getCssName('bits-post-chat-body'));
  this.dom_.setTextContent(bodyDiv, this.body);

  element.appendChild(nicknameDiv);
  element.appendChild(separatorDiv);
  element.appendChild(bodyDiv);
};


bits.posts.Post.prototype.renderPresence = function(element) {
  // TODO: HTML escaping.
  goog.dom.classes.add(element, goog.getCssName('bits-post-presence'));

  var bodyDiv = this.dom_.createElement('span');
  goog.dom.classes.add(bodyDiv, goog.getCssName('bits-post-presence-body'));
  this.dom_.setTextContent(bodyDiv, this.body);

  element.appendChild(bodyDiv);
};


/**
 * Decorates an existing HTML DIV element as a Post.
 *
 * @param {HTMLElement} element The DIV element to decorate.
 */
bits.posts.Post.prototype.decorateInternal = function(element) {
  bits.posts.Post.superClass_.decorateInternal.call(this, element);

  // TODO: Make it unfocusable for key input.

  var elem = this.getElement();
  elem.tabIndex = 0;
  this.setAllowTextSelection(true);
};


/**
 * Disposes of the component.
 */
bits.posts.Post.prototype.disposeInternal = function() {
  bits.posts.Post.superClass_.disposeInternal.call(this);
  this.eh_.dispose();
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
 * @constructor
 */
bits.posts.PostContainer = function(shardId, opt_archiveType) {
  goog.base(this);

  this.logger_ = goog.debug.Logger.getLogger('bits.posts.PostContainer');
  this.shardId = shardId
  if (!opt_archiveType) {
    opt_archiveType = null;
  }
  this.archiveType = opt_archiveType;

  // Subscribe to internal events.
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.PostReceived,
      this.handlePostReceived, this);
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.SubmittedPostSent,
      this.handlePostSubmitted, this);
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.SubmittedPostReceived,
      this.handleSubmitPostSuccess, this);
  bits.events.PubSub.subscribe(
      this.shardId, bits.events.EventType.RosterReceived,
      this.handleRosterReceived, this);

  // Keep track of the list of Posts we have already seen. Keys are IDs
  // unique to each post but separate from the sequence numbers because
  // IDs have no ordering. When a user posts a message they will insert the
  // Post into their own PostContainer immediately after it's received by the
  // server side. Then when the post comes through over the channel the Post's
  // sequence number (thus far missing/unassigned) will be updated to match
  // the server's assignment.
  this.postIdMap = new goog.structs.Map();

  // Lowest sequence number that is present in this container.
  this.lowestSequenceId = null;

  /**
   * Event handler for this object.
   * @type {goog.events.EventHandler}
   * @private
   */
  this.eh_ = new goog.events.EventHandler(this);

  this.container = new goog.ui.Container();
  this.container.setFocusableChildrenAllowed(false);
  this.container.setFocusable(true);
}
goog.inherits(bits.posts.PostContainer, goog.ui.Component);


bits.posts.PostContainer.prototype.handlePostSubmitted = function(postMap) {
  this.logger_.info('User-submitted post sent: ' +
                    'shardId="' + postMap.shardId +
                    '", postId="' + postMap.postId +
                    '", nickname="' + postMap.nickname + '"');
  // TODO: Filter by archive type.
  this.addOrUpdatePost(new bits.posts.Post(postMap));
};


bits.posts.PostContainer.prototype.handleSubmitPostSuccess =
function(postMap) {
  this.logger_.info('User-submitted post received by server: ' +
                    'shardId="' + postMap.shardId +
                    '", postId="' + postMap.postId +
                    '", nickname="' + postMap.nickname + '"');
  this.addOrUpdatePost(new bits.posts.Post(postMap));
};


bits.posts.PostContainer.prototype.handlePostReceived = function(postMap) {
  this.logger_.info('External post received from server: ' +
                    'shardId="' + postMap.shardId +
                    '", postId="' + postMap.postId +
                    '", sequenceId="' + postMap.sequenceId +
                    '", nickname="' + postMap.nickname + '"');
  this.addOrUpdatePost(new bits.posts.Post(postMap));
};


bits.posts.PostContainer.prototype.handleRosterReceived = function(postMap) {
  this.logger_.info('Received roster from server: ' +
                    'shardId="' + postMap.shardId +
                    '", body="' + postMap.body + '"');
  this.addOrUpdatePost(new bits.posts.Post(postMap));
};


bits.posts.PostContainer.prototype.prependPosts = function(postList) {
  if (postList.length == 0) return;

  // Sort in descending sequence order, newest to oldest.
  goog.array.sort(postList, function(a, b) {
    return b.sequenceId - a.sequenceId;
  });

  // Update the oldest sequence number that we know of.
  if (postList[postList.length - 1].sequenceId < this.lowestSequenceId) {
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
      // post has been added.
      this.container.getElement().scrollTop +=
          scrollHeightAfter - scrollHeightBefore;
    }
  }, this);
};

bits.posts.PostContainer.prototype.addOrUpdatePost = function(post) {
  var scrollAtBottom =
      this.container.getElement().scrollHeight ==
      (this.container.getElement().scrollTop +
       this.container.getElement().clientHeight);

  if (post.sequenceId && post.sequenceId < this.lowestSequenceId) {
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
 * Creates an initial DOM representation for the component.
 */
bits.posts.PostContainer.prototype.createDom = function() {
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
  this.container.decorate(elem);
  goog.style.setUnselectable(elem, false, goog.userAgent.GECKO);
  new goog.ui.ContainerScroller(this.container);
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
};


/**
 * Called when component's element is known to have been removed from the
 * document.
 */
bits.posts.PostContainer.prototype.exitDocument = function() {
  bits.posts.PostContainer.superClass_.exitDocument.call(this);
};
