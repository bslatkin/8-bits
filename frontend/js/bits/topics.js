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
goog.provide('bits.topics.TopicPrompt');

goog.require('goog.array');
goog.require('goog.date.DateTime');
goog.require('goog.debug.Logger');
goog.require('goog.dom');
goog.require('goog.events');
goog.require('goog.events.EventHandler');
goog.require('goog.structs.Map');
goog.require('goog.style');
goog.require('goog.ui.Component');
goog.require('goog.ui.Container');
goog.require('goog.ui.ContainerScroller');
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
  this.shardId = topicMap['shardId'] || null;

  /**
   * @type {string}
   * @private
   */
  this.createdNickname = topicMap['createdNickname'] || null;

  /**
   * @type {string}
   * @private
   */
  this.url = topicMap['url'] || null;

  /**
   * @type {string}
   * @private
   */
  this.description = topicMap['description'] || null;

  /**
   * @type {number?}
   * @private
   */
  this.updateTimeMs = topicMap['updateTimeMs'] || null;

  /**
   * @type {goog.date.DateTime}
   * @private
   */
  this.updateDateTime = null;
  if (this.updateTimeMs) {
    this.updateDateTime = new goog.date.DateTime();
    this.updateDateTime.setTime(this.updateTimeMs_);
  }

};
goog.inherits(bits.topics.Topic, goog.ui.Control);


/**
 * Creates an initial DOM representation for the component.
 */
bits.topics.Topic.prototype.createDom = function() {
  var element = this.dom_.createDom('div', 'bits-topic');

  var containerEl = this.dom_.createDom('div', 'bits-topic-title-c');

  var nicknameEl = this.dom_.createDom('span', 'bits-topic-nickname');
  nicknameEl.innerHTML = this.createdNickname;

  var separatorEl = this.dom_.createDom('span', 'bits-topic-separator');
  this.dom_.setTextContent(separatorEl, ': ');

  var titleEl = this.dom_.createDom('a', 'bits-topic-title');
  titleEl.href = this.url;
  titleEl.setAttribute('target', '_blank');
  this.dom_.setTextContent(
      titleEl,
      this.url.replace(/http(s?):\/\/(www\.)?([^ '"\)\(]+)/g, '$3'));

  containerEl.appendChild(nicknameEl);
  containerEl.appendChild(separatorEl);
  containerEl.appendChild(titleEl);

  var descriptionEl = this.dom_.createDom('div', 'bits-topic-description');
  descriptionEl.innerHTML = this.description;

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

  this.setSupportedState(goog.ui.Component.State.OPENED, true);

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
   * @type {goog.structs.Map}
   * @private
   */
  this.topicIdMap_ = new goog.structs.Map();

  /**
   * @type {goog.ui.Container}
   * @private
   */
  this.container_ = new goog.ui.Container();
  this.container_.setFocusableChildrenAllowed(false);
  this.container_.setFocusable(false);
  this.registerDisposable(this.container_);

  /**
   * @type {bits.topics.Topic}
   * @private
   */
  this.activeTopic_ = null;

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

  this.dom_.appendChild(
      element,
      this.dom_.createDom('div', 'bits-topic-menu-dropdown'));

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
  //
  // What else: Need a disclosure triangle
  // Need a message to say how to start a topic if there are none. Or maybe
  // the menu doesn't show until the first topic arrives?

  this.decorateInternal(element);
};


/**
 * Decorates an existing HTML DIV element.
 *
 * @param {HTMLElement} element The DIV element to decorate.
 */
bits.topics.TopicMenu.prototype.decorateInternal = function(element) {
  bits.topics.TopicMenu.superClass_.decorateInternal.call(this, element);

  var elem = this.getElement();

  var dropdownEl = this.dom_.getElementByClass(
      'bits-topic-menu-dropdown', elem);
  this.container_.decorate(dropdownEl);
  var scroller = new goog.ui.ContainerScroller(this.container_);
  this.registerDisposable(scroller);

  this.setOpen(false);
  this.setAllowTextSelection(true);
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


/**
 *
 */
bits.topics.TopicMenu.prototype.addTopic = function(topic) {
  this.container_.addChild(topic, true);
  this.topicIdMap_.set(topic.shardId, topic);
  this.eh_.listen(
      topic, goog.ui.Component.EventType.ACTION, this.handleTopicClick);
  this.sortChildren_();
};


/**
 *
 */
bits.topics.TopicMenu.prototype.sortChildren_ = function() {
  var children = [];
  this.container_.forEachChild(function(c) { children.push(c) });
  goog.array.sort(children, function(a, b) {
    if (a.updateTimeMs && b.updateTimeMs) {
      return a.updateTimeMs - b.updateTimeMs;
    }
    if (a.updateTimeMs && !b.updateTimeMs) {
      return 1;
    }
    if (!a.updateTimeMs && b.updateTimeMs) {
      return -1;
    }
    return 0;
  });
  for (var i = 0, n = children.length; i < n; i++) {
    this.container_.addChildAt(children[i], i);
  }
};


/**
 *
 */
bits.topics.TopicMenu.prototype.selectTopic = function(shardId) {
  var topic = this.topicIdMap_.get(shardId);
  if (!topic) {
    return;
  }

  if (this.activeTopic_) {
    this.removeChild(this.activeTopic_);
    this.container_.addChild(this.activeTopic_);
    goog.dom.classes.remove(
        this.activeTopic_.getElement(), 'bits-topic-selected');
    this.sortChildren_();
  }

  this.container_.removeChild(topic);
  this.addChildAt(topic, 0);
  goog.dom.classes.add(topic.getElement(), 'bits-topic-selected');
  this.activeTopic_ = topic;
};


/**
 *
 */
bits.topics.TopicMenu.prototype.setOpen = function(open) {
  bits.topics.TopicMenu.superClass_.setOpen.call(this, open);
  this.container_.setVisible(this.isOpen());
};


/**
 *
 */
bits.topics.TopicMenu.prototype.handleTopicClick = function(event) {
  if (event.target != this.activeTopic_) {
    this.selectTopic(event.target.shardId);
  }
};
