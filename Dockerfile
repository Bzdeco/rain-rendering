FROM ic-registry.epfl.ch/cvlab/gwizdala/lab-pytorch:cuda117

# Python dependencies for rain rendering
RUN pip install --no-cache-dir glob2
RUN pip install --no-cache-dir pyclipper
RUN pip install --no-cache-dir imutils

# OpenSceneGraph installation
RUN cp /etc/apt/sources.list /etc/apt/sources.list~
RUN sed -Ei 's/^# deb-src /deb-src /' /etc/apt/sources.list
RUN apt-get update

# Install OSG dependencies
RUN apt-get build-dep -y openscenegraph

# Build OSG 3.4.1 from source
RUN mkdir -p /home/bzdeco/ && cd /home/bzdeco/
RUN git clone https://github.com/openscenegraph/osg && cd osg && git checkout tags/OpenSceneGraph-3.4.1
WORKDIR osg
RUN cmake .
RUN make -j6
RUN make install

# Set environment variables for OSG
RUN echo 'export LD_LIBRARY_PATH="/usr/lib64:/usr/local/lib64:/usr/lib:/usr/local/lib:$LD_LIBRARY_PATH"' >> ~/.profile
RUN echo 'export OPENTHREADS_INC_DIR="/usr/include:/usr/local/include"' >> ~/.profile
RUN echo 'export OPENTHREADS_LIB_DIR="/usr/lib64:/usr/local/lib64:/usr/lib:/usr/local/lib"' >> ~/.profile
RUN echo 'export PATH="$OPENTHREADS_LIB_DIR:$PATH"' >> ~/.profile
RUN . ~/.profile

# Setup OSG data
WORKDIR /
RUN git clone https://github.com/openscenegraph/osg-data
RUN mkdir -p /usr/local/OpenSceneGraph/data && cp -r osg-data/* /usr/local/OpenSceneGraph/data
RUN echo 'export OSG_FILE_PATH="/usr/local/OpenSceneGraph/data:/usr/local/OpenSceneGraph/data/Images"' >> ~/.profile
RUN . ~/.profile

# Boost installation
RUN wget -O boost_1_62_0.tar.gz https://sourceforge.net/projects/boost/files/boost/1.62.0/boost_1_62_0.tar.gz/download
RUN tar xzvf boost_1_62_0.tar.gz
WORKDIR boost_1_62_0
RUN apt-get install -y build-essential g++ python3-dev autotools-dev libicu-dev libbz2-dev
RUN ./bootstrap.sh --prefix=/usr/local
RUN user_configFile=`find $PWD -name user-config.jam` && echo "using mpi ;" >> $user_configFile

# Fixed issue according to https://stackoverflow.com/a/54991698
COPY builtin_converters.cpp /boost_1_62_0/libs/python/src/converter
RUN ./b2 -q --with=all install  # -j6 to speedup
RUN sh -c 'echo "/usr/local/lib" >> /etc/ld.so.conf.d/local.conf'
RUN ldconfig

RUN pip install --no-cache-dir pyproj
RUN pip install --no-cache-dir numpy-quaternion

# OpenCV - initial setup
RUN apt install -y build-essential cmake git pkg-config libgtk-3-dev \
    libavcodec-dev libavformat-dev libswscale-dev libv4l-dev \
    libxvidcore-dev libx264-dev libjpeg-dev libpng-dev libtiff-dev \
    gfortran openexr libatlas-base-dev python3-dev python3-numpy \
    libtbb2 libtbb-dev libdc1394-22-dev
RUN mkdir /opencv_build && cd /opencv_build
WORKDIR /opencv_build
RUN git clone https://github.com/opencv/opencv.git && cd opencv && git checkout 3.2.0
RUN git clone https://github.com/opencv/opencv_contrib.git && cd opencv_contrib && git checkout 3.2.0

# Build OpenCV
RUN mkdir /opencv_build/opencv/build
WORKDIR /opencv_build/opencv/build

RUN cmake -D CMAKE_BUILD_TYPE=RELEASE \
    -D CMAKE_INSTALL_PREFIX=/usr/local \
    -D INSTALL_C_EXAMPLES=ON \
    -D INSTALL_PYTHON_EXAMPLES=ON \
    -D OPENCV_GENERATE_PKGCONFIG=ON \
    -D OPENCV_EXTRA_MODULES_PATH=/opencv_build/opencv_contrib/modules \
    -D BUILD_EXAMPLES=ON .. \
#    -D CMAKE_LIBRARY_PATH=/usr/local/cuda/lib64/stubs \
    -DWITH_CUDA:BOOL="0"
#    -D CUDA_nppi_LIBRARY=true \
#    -D OPENCV_CUDA_FORCE_BUILTIN_CMAKE_MODULE=ON
RUN echo '#define AV_CODEC_FLAG_GLOBAL_HEADER (1 << 22)\n#define CODEC_FLAG_GLOBAL_HEADER AV_CODEC_FLAG_GLOBAL_HEADER\n#define AVFMT_RAWPICTURE 0x0020' | cat - ../modules/videoio/src/cap_ffmpeg_impl.hpp > temp && mv temp ../modules/videoio/src/cap_ffmpeg_impl.hpp
RUN make opencv_python3
RUN make
#RUN make install
