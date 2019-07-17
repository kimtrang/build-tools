#!/bin/bash

MANIFEST=${1}
PRODUCT='Couchbase-Lite-Android'

repo init -u git://github.com/couchbase/manifest -m  couchbase-lite-android/${MANIFEST} -g all
repo sync --jobs=6 

# clean up
for i in .repo .git fleece Docs doc test tests docs googletest third_party _obsolete; do
     find . -type d -name $i | xargs rm -rf
done
rm -rf couchbase-lite-android/tools/upgradetest

# setup require gradle tools for BL to run ./gradlew lib:dependencies
SDK_DIR=/home/couchbase/tools/android-sdk
NDK_DIR=/home/couchbase/tools/android-ndk-r20
export ANDROID_HOME=$SDK_DIR
export ANDROID_SDK_HOME=$SDK_DIR
export ANDROID_NDK_HOME=$NDK_DIR
export PATH=$PATH:$SDK_DIR/tools:$SDK_DIR/platform-tools

BUILD_DIR=${WORKSPACE}/couchbase-lite-android-ee

echo "cd ${BUILD_DIR} ..."
echo

cd ${BUILD_DIR}

if [ ! -f "local.properties" ]; then
	echo "ndk.dir=${NDK_DIR}" > local.properties
    echo "sdk.dir=${SDK_DIR}" >> local.properties
fi

cp local.properties ${WORKSPACE}/local.properties

export PATH=$PATH:/usr/local/go/bin
bash <(curl -s https://detect.synopsys.com/detect.sh) \
--detect.project.name="PRODUCT" \
--detect.project.version.name=${VERSION} \
--detect.project.codelocation.prefix="PRODUCT" \
--detect.source.path=${WORKSPACE} \
--logging.level.com.synopsys.integration=DEBUG \
--blackduck.url=https://blackduck.build.couchbase.com \
--blackduck.username=sysadmin \
--blackduck.password=${BLACDUCK} \
--blackduck.trust.cert=true  \
--detect.excluded.detector.types=NPM \
--detect.cleanup=${DETECT_CLEANUP} \
--detect.diagnostic.mode=${DIAGNOSTIC_MODE}
