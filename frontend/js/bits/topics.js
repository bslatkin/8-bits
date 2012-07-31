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
 * @fileoverview Topic menu and related components.
 */

goog.provide('bits.topics.TopicMenu');

goog.require('goog.dom');
goog.require('goog.style');
goog.require('goog.ui.Component');

goog.require('bits.events');


/**
 * Creates a topic menu
 * @constructor
 */
bits.topics.TopicMenu = function(shardId) {
  goog.base(this);

  /**
   * @type {string}
   * @private
   */
  this.shardId_ = shardId;

  /**
   * @type {goog.events.EventHandler}
   * @private
   */
  this.eh_ = new goog.events.EventHandler(this);
}
goog.inherits(bits.topics.TopicMenu, goog.ui.Component);


/**
 * Decorates an existing HTML DIV element.
 *
 * @param {HTMLElement} element The DIV element to decorate.
 */
bits.topics.TopicMenu.prototype.decorateInternal = function(element) {
  bits.topics.TopicMenu.superClass_.decorateInternal.call(this, element);
};


/**
 * Disposes of the component.
 */
bits.topics.TopicMenu.prototype.disposeInternal = function() {
  bits.topics.TopicMenu.superClass_.disposeInternal.call(this);
  this.eh_.dispose();
};


/**
 * Called when component's element is known to be in the document.
 */
bits.topics.TopicMenu.prototype.enterDocument = function() {
  bits.topics.TopicMenu.superClass_.enterDocument.call(this);

};


/**
 * Called when component's element is known to have been removed from the
 * document.
 */
bits.topics.TopicMenu.prototype.exitDocument = function() {
  bits.topics.TopicMenu.superClass_.exitDocument.call(this);
};

