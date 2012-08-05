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

goog.provide('bits.topics.Topic');
goog.provide('bits.topics.TopicMenu');

goog.require('goog.date.DateTime');
goog.require('goog.debug.Logger');
goog.require('goog.dom');
goog.require('goog.style');
goog.require('goog.ui.Control');

goog.require('bits.events');


/**
 * A topic to display in the topic menu.
 *
 * @param {object} topicMap Map of topic attributes.
 * @extends {goog.ui.Control}
 * @constructor
 */
bits.topics.Topic = function(topicMap) {
  goog.base(this);

  /**
   * @type {string}
   * @private
   */
  this.shardId_ = topicMap['shardId'] || null;

  /**
   * @type {string}
   * @private
   */
  this.createdNickname_ = topicMap['createdNickname'] || null;

  /**
   * @type {string}
   * @private
   */
  this.url_ = topicMap['url'] || null;

  /**
   * @type {string}
   * @private
   */
  this.description_ = topicMap['description'] || null;

  /**
   * @type {number?}
   * @private
   */
  this.updateTimeMs_ = topicMap['updateTimeMs'] || null;

  /**
   * @type {goog.date.DateTime}
   * @private
   */
  this.updateDateTime_ = null;
  if (this.updateTimeMs_) {
    this.updateDateTime_ = new goog.date.DateTime();
    this.updateDateTime_.setTime(this.updateTimeMs_);
  }

};
goog.inherits(bits.topics.Topic, goog.ui.Control);


/**
 * Creates an initial DOM representation for the component.
 */
bits.topics.Topic.prototype.createDom = function() {
  var element = this.dom_.createElement('div');
  goog.dom.classes.add(element, goog.getCssName('bits-topic'));

  var containerEl = this.dom_.createElement('div');
  goog.dom.classes.add(containerEl, goog.getCssName('bits-topic-title-c'));

  var nicknameEl = this.dom_.createElement('span');
  goog.dom.classes.add(nicknameEl, goog.getCssName('bits-topic-nickname'));
  nicknameEl.innerHTML = this.createdNickname_;

  var separatorEl = this.dom_.createElement('span');
  goog.dom.classes.add(separatorEl, goog.getCssName('bits-topic-separator'));
  this.dom_.setTextContent(separatorEl, ': ');

  var titleEl = this.dom_.createElement('a');
  goog.dom.classes.add(titleEl, goog.getCssName('bits-topic-title'));
  titleEl.href = this.url_;
  titleEl.setAttribute('target', '_blank');
  titleEl.innerText = this.url_.replace(
      /http(s?):\/\/(www\.)?([^ '"\)\(]+)/g, '$3');

  containerEl.appendChild(nicknameEl);
  containerEl.appendChild(separatorEl);
  containerEl.appendChild(titleEl);

  var descriptionEl = this.dom_.createElement('div');
  goog.dom.classes.add(descriptionEl, goog.getCssName('bits-topic-description'));
  descriptionEl.innerHTML = this.description_;

  element.appendChild(containerEl);
  element.appendChild(descriptionEl);
  this.decorateInternal(element);
};


/**
 * Decorates an existing HTML DIV element as a Post.
 *
 * @param {HTMLElement} element The DIV element to decorate.
 */
bits.topics.Topic.prototype.decorateInternal = function(element) {
  bits.topics.Topic.superClass_.decorateInternal.call(this, element);

  var elem = this.getElement();
  elem.tabIndex = 0;
  this.setAllowTextSelection(true);
};


/**
 * Disposes of the component.
 */
bits.topics.Topic.prototype.disposeInternal = function() {
  bits.topics.Topic.superClass_.disposeInternal.call(this);
};


/**
 * Called when component's element is known to be in the document.
 */
bits.topics.Topic.prototype.enterDocument = function() {
  bits.topics.Topic.superClass_.enterDocument.call(this);
};


/**
 * Called when component's element is known to have been removed from the
 * document.
 */
bits.topics.Topic.prototype.exitDocument = function() {
  bits.topics.Topic.superClass_.exitDocument.call(this);
};



/**
 * Creates a topic menu
 * @extends {goog.ui.Component}
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
   * @type {goog.debug.Logger}
   * @private
   */
  this.logger_ = goog.debug.Logger.getLogger(
      'bits.topics.TopicMenu:' + shardId);

  /**
   * @type {goog.events.EventHandler}
   * @private
   */
  this.eh_ = new goog.events.EventHandler(this);
}
goog.inherits(bits.topics.TopicMenu, goog.ui.Control);


/**
 * Creates an initial DOM representation for the component.
 */
bits.topics.TopicMenu.prototype.createDom = function() {
  var element = this.dom_.createDom('div', 'bits-topic-menu');

  // create the pop-over div that will hover below when this is popped open
  // make that div scrollable
  // children go in that div by default, whatever gets selected goes back
  // in that div, and then the div is resorted by update time
  // default state is the no topic selected with help message on how to start
  // a topic.
  // main component has a topic under it and also a down arrow to indicate
  // that you can expand it. if you click anywhere on the item it will cause
  // the menu to open. click off anywhere and it will close.
  // click on a child and they will swap, the menu will close, and then a
  // topic change will fire.

  this.decorateInternal();
};


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

