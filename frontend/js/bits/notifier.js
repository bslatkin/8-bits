// Copyright 2012 Brett Slatkin
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
 * @fileoverview Responsible for notifying the user about new posts using
 * icons, sounds, push notifications, etc.
 */

goog.provide('bits.notifier.Notifier');

goog.require('goog.debug.Logger');
goog.require('goog.dom');
goog.require('goog.dom.dataset');
goog.require('goog.structs.Set');
goog.require('goog.style');
goog.require('goog.Timer');

goog.require('bits.events');
goog.require('bits.posts.ArchiveType');


/**
 * Constructs a new Notifier object.
 * @param {string} shardId ID of the shard to notify for.
 * @constructor
 */
bits.notifier.Notifier = function(shardId) {
  goog.base(this);

  /**
   * @type {goog.debug.Logger}
   * @private
   */
  this.logger_ = goog.debug.Logger.getLogger('bits.notifier.Notifier');

  /**
   * @type {string}
   * @private
   */
  this.shardId_ = shardId;

  var favEl = goog.dom.getElement('favicon');

  /**
   * @type {string}
   * @private
   */
  this.normalFaviconUrl_ = favEl.getAttribute('href');

  /**
   * @type {string}
   * @private
   */
  this.flashFaviconUrl_ = goog.dom.dataset.get(favEl, 'flashUrl');

  /**
   * @type {boolean}
   * @private
   */
  this.active_ = true;

  /**
   * @type {boolean}
   * @private
   */
  this.flashing_ = false;

  /**
   * @type {goog.structs.Set}
   * @private
   */
  this.sentPosts_ = new goog.structs.Set();

  /**
   * @type {goog.events.EventHandler}
   * @private
   */
  this.eh_ = new goog.events.EventHandler(this);

  /**
   * @type {goog.Timer}
   * @private
   */
  this.flashTimer_ = new goog.Timer(
        bits.notifier.Notifier.FLASH_PERIOD_INVERTED);

  this.eh_.listen(this.flashTimer_, goog.Timer.TICK, this.handleTimer_);

  this.eh_.listen(window, goog.events.EventType.FOCUS,
                  goog.bind(this.handleWindowFocus_, this, true), true);
  this.eh_.listen(window, goog.events.EventType.BLUR,
                  goog.bind(this.handleWindowFocus_, this, false), true);

  bits.events.PubSub.subscribe(
      this.shardId_, bits.events.EventType.SubmittedPostSent,
      this.handlePostSent_, this);

  bits.events.PubSub.subscribe(
      this.shardId_, bits.events.EventType.PostReceived,
      this.handlePostReceived_, this);
}
goog.inherits(bits.notifier.Notifier, goog.Disposable);


/**
 * Duration of the normal favicon when flashing.
 * @type {number}
 */
bits.notifier.Notifier.FLASH_PERIOD_NORMAL = 2000;


/**
 * Duration of the inverted favicon when flashing.
 * @type {number}
 */
bits.notifier.Notifier.FLASH_PERIOD_INVERTED = 1000;


/**
 * Disposes of the object.
 */
bits.notifier.Notifier.prototype.disposeInternal = function() {
  bits.notifier.Notifier.superClass_.disposeInternal.call(this);
  this.shardId_ = null;
  // TODO(bslatkin): Unsubscribe from events.
};


/**
 * Sets the favicon's state.
 * @param {boolean} flashing True if it should be flashing, false if not.
 * @private
 */
bits.notifier.Notifier.prototype.setFlashing_ = function(flashing) {
  var href = this.normalFaviconUrl_;
  if (flashing) {
    href = this.flashFaviconUrl_;
  }

  var el = goog.dom.getElement('favicon');
  el.href = href;

  this.flashing_ = flashing;
};


/**
 * Handles when a new post is sent to the server side.
 * @param {object} postMap Post that was received.
 * @private
 */
bits.notifier.Notifier.prototype.handlePostSent_ = function(postMap) {
  if (postMap['archiveType'] == bits.posts.ArchiveType.CHAT) {
    this.sentPosts_.add(postMap['postId']);
  }
};


/**
 * Handles when new posts are received.
 * @param {object} postMap Post that was received.
 * @private
 */
bits.notifier.Notifier.prototype.handlePostReceived_ = function(postMap) {
  if (this.active_) {
    return;
  }

  if (postMap['archiveType'] != bits.posts.ArchiveType.CHAT) {
    return;
  }

  if (this.flashTimer_.enabled) {
    return;
  }

  var postId = postMap['postId'];

  // Don't notify for posts we recently sent ourselves.
  if (this.sentPosts_.contains(postId)) {
    // Make sure memory doesn't get out of hand.
    if (this.sentPosts_.getCount() > 1000) {
      this.sentPosts_.clear();
    }
    this.logger_.info('Notifier ignoring local postId=' + postId);
    return;
  }

  this.logger_.info('Notifier signalling for postId=' + postId);
  this.setFlashing_(true);
  this.flashTimer_.start();
};


/**
 * Handles when the window changes focus.
 * @param {boolean} focused True if the window is now focused, false if it
 *   has become unfocused.
 * @private
 */
bits.notifier.Notifier.prototype.handleWindowFocus_ = function(focused) {
  this.active_ = focused;
  if (this.active_ && this.flashTimer_.enabled) {
    this.flashTimer_.stop();
    this.setFlashing_(false);
  }
};


/**
 * Handles the flashing timer.
 * @private
 */
bits.notifier.Notifier.prototype.handleTimer_ = function(e) {
  if (this.flashing_) {
    this.flashTimer_.setInterval(bits.notifier.Notifier.FLASH_PERIOD_NORMAL);
  } else {
    this.flashTimer_.setInterval(bits.notifier.Notifier.FLASH_PERIOD_INVERTED);
  }

  this.setFlashing_(!this.flashing_);
};
