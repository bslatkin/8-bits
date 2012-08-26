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
 * @fileoverview Common utility functions.
 */

goog.provide('bits.util');


/**
 * Pattern used to match links.
 * @type {string}
 * @private
 * @const
 */
bits.util.LINK_PATTERN_ = '(http(s?):\\/\\/[^ \'"\\)\\(]+)';


/**
 * Regular expression used to match links.
 * @type {RegExp}
 * @private
 * @const
 */
bits.util.LINK_MATCH_RE_ = new RegExp('^' + bits.util.LINK_PATTERN_ + '$');


/**
 * Regular expression used to replace links.
 * @type {RegExp}
 * @private
 * @const
 */
bits.util.LINK_SUB_RE_ = new RegExp(bits.util.LINK_PATTERN_, 'g');


/**
 * Determines if the given string contains only a link.
 * @param {string} text Text that is a link
 * @return {boolean} True if the string is a link, false otherwise.
 */
bits.util.matchLink = function(text) {
  return text.match(bits.util.LINK_MATCH_RE_);
};


/**
 * Replaces the links in the given text with a substitution string.
 * @param {string} text Text that may contain links.
 * @param {string} sub What to use as a replacement. May use '$1' to refer
 *   to the link that was matched.
 * @return {string} The rewritten string.
 */
bits.util.rewriteLink = function(text, sub) {
  // TODO: Support obvious links that start with www or have 'w.xyz/' in them.
  return text.replace(bits.util.LINK_SUB_RE_, sub);
};
