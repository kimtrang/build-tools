#!/bin/bash -ex

MANIFEST=$1

# Check out the main source code
#repo init -u git://github.com/couchbase/manifest -g all -m couchbase-server/${MANIFEST}
repo init -u git://github.com/couchbase/manifest -g all -m ${MANIFEST}
repo sync --jobs=6

# Clone cbdeps (really need to clean this up)
mkdir cbdeps
cd cbdeps
git clone git://github.com/couchbasedeps/breakpad
(cd breakpad && git checkout 1e455b5)
git clone git://github.com/couchbasedeps/curl -b curl-7_49_1
git clone git://github.com/couchbasedeps/erlang -b couchbase-watson
git clone git://github.com/couchbasedeps/flatbuffers -b v1.2.0
git clone git://github.com/couchbasedeps/icu4c -b r54.1
git clone git://github.com/couchbasedeps/jemalloc -b 4.1.1-couchbase2
git clone git://github.com/couchbasedeps/libevent -b release-2.0.22-stable
git clone git://github.com/couchbasedeps/pysqlite2
(cd pysqlite2 && git checkout 0ff6e32)
git clone git://github.com/couchbasedeps/python-snappy
(cd python-snappy && git checkout c97d633)
git clone git://github.com/couchbasedeps/snappy -b 1.1.1
git clone git://github.com/couchbasedeps/v8 -b 5.2-couchbase

# cbdeps-specific pruning

rm -rf erlang/lib/*test*

# tree-sitter, gyp, ngyp
rm -rf breakpad/src/tools/gyp
rm -rf v8/tools/gyp
rm -rf v8/build
rm -rf icu4c/win_binary
(cd v8 && rm -rf third_party/binutils/ third_party/icu/ third_party/llvm-build/ buildtools/ test)

# Prune things to fit in our 1GB source code limit
cd ..
find . -type d -name .git -print0 | xargs -0 rm -rf
rm -rf .repo

# cleanup unwanted stuff
rm -rf testrunner
rm -rf goproj/src/github.com/couchbase/query/data/sampledb
rm -rf goproj/src/github.com/couchbase/indexing/secondary/docs

# Ejecta
rm -rf cbbuild/tools/iOS

# rebar
rm -f tlm/cmake/Modules/rebar

# Sample data, testing code, etc
find . -type d -name test -print0 | xargs -0 rm -rf
find . -type d -name gtest -print0 | xargs -0 rm -rf
find . -type d -name testing -print0 | xargs -0 rm -rf
find . -type d -name \*tests -print0 | xargs -0 rm -rf
find . -type d -name data -print0 | xargs -0 rm -rf
find . -type d -name docs -print0 | xargs -0 rm -rf
find . -type d -name examples -print0 | xargs -0 rm -rf
find . -type d -name samples -print0 | xargs -0 rm -rf
find . -type d -name benchmarks -print0 | xargs -0 rm -rf
