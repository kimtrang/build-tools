#!/bin/bash -ex
# Server code

# Check out the main source code
repo init -u git://github.com/couchbase/manifest -g all -m couchbase-server/${MANIFEST}
repo sync --jobs=6

# cbdeps-specific pruning

rm -rf erlang/lib/*test*

# extra libs in boost-1.67.0
for i in asio fusion geometry hana phoenix spirit typeof; do
    rm -rf boost/boost-dist/libs/$i
done
rm -rf boost/boost-dist/doc

# tree-sitter, gyp, ngyp
rm -rf breakpad/src/tools/gyp
rm -rf v8/tools/gyp
rm -rf v8/build
rm -rf icu4c/win_binary
(pushd v8 && rm -rf third_party/binutils/ third_party/icu/ third_party/llvm-build/ buildtools/ test && popd)

# Prune things to fit in our 1GB source code limit
find . -type d -name .git -or -name .repo -print0 | xargs -0 rm -rf

# cleanup unwanted stuff
rm -rf testrunner
rm -rf goproj/src/github.com/couchbase/query/data/sampledb
rm -rf goproj/src/github.com/couchbase/docloader/examples
rm -rf goproj/src/github.com/couchbase/indexing/secondary/docs

# Ejecta
rm -rf cbbuild/tools/iOS

# rebar
rm -f tlm/cmake/Modules/rebar

# Sample data, testing code, etc
rm -rf analytics/asterixdb/asterixdb/asterix-examples
rm -rf analytics/asterixdb/asterixdb/asterix-app/data
rm -rf analytics/cbas/cbas-test
find . -type d -name test -print0 | xargs -0 rm -rf
find . -type d -name testdata -print0 | xargs -0 rm -rf
find . -type d -name gtest -print0 | xargs -0 rm -rf
find . -type d -name testing -print0 | xargs -0 rm -rf
find . -type d -name \*tests -print0 | xargs -0 rm -rf
find . -type d -name data -print0 | xargs -0 rm -rf
find . -type d -name docs -print0 | xargs -0 rm -rf
find . -type d -name examples -print0 | xargs -0 rm -rf
find . -type d -name samples -print0 | xargs -0 rm -rf
find . -type d -name benchmarks -print0 | xargs -0 rm -rf

# Remove extra build tools for V2 deps
find . -type d -name cbbuild -or -name build-tools | xargs rm -rf

# Run required tools

for i in `find . -type f -name package.json`; do pushd `dirname $i`; npm install; ls -la node_modules; popd; done

