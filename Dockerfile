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

# Not installing OpenCV as it is already installed in this image