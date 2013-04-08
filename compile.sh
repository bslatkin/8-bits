#!/bin/bash
#
# Copyright 2012 Brett Slatkin, Nathan Naze
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Generates a Closure compiled.js file for the bits.* namespaces.
echo "Compiling JavaScript"
python ./closure-library/closure/bin/build/closurebuilder.py  \
  --root="./frontend/js/bits" \
  --root="./closure-library" \
  --namespace="bits.startup" \
  --output_mode="compiled" \
  --compiler_jar="./closure-compiler.jar" \
  --output_file="frontend/js/bits/compiled.js" \
  --compiler_flags="--compilation_level=SIMPLE_OPTIMIZATIONS"

# TODO(bslatkin): Use --compilation_level=ADVANCED_OPTIMIZATIONS

# Put all the CSS in one file.
echo "Combining CSS"
find frontend/css -name '*.css' \
  -and -not -name 'compiled.css' \
  -and -not -name 'ie.css' \
  -and -not -name 'screen.css' \
  -and -not -name 'print.css' \
  | xargs cat > frontend/css/compiled.css
