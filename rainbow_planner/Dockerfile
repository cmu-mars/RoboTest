#Use multisage build to build rainbow and then create the cp1 image
FROM ubuntu:16.04 as rainbow-builder
ARG rainbow_version=BRASS3.0
RUN apt update  
RUN apt-get install --no-install-recommends --fix-missing -y software-properties-common zip unzip tar gzip make wget curl bash git-core

# To ensure the right versions of the libraries in the build
# we need to FROM the same root, so that means installing Java
# and Maven manually

#RUN \                                                                       
# echo oracle-java10-installer shared/accepted-oracle-license-v1-1 select true | debconf-set-selections && \
#  add-apt-repository -y ppa:webupd8team/java && \
#   apt-get update && \
#    apt-get install -y oracle-java10-installer --allow-unauthenticated && \
#     rm -rf /var/lib/apt/lists/* && \
#      rm -rf /var/cache/oracle-jdk10-installer
RUN apt-get install -y openjdk-8-jdk
# Install MAven
ARG MAVEN_VERSION=3.3.9
ARG USER_HOME_DIR="/root"
RUN mkdir -p /usr/share/maven && \
    curl -fsSL http://apache.osuosl.org/maven/maven-3/$MAVEN_VERSION/binaries/apache-maven-$MAVEN_VERSION-bin.tar.gz | tar -xzC /usr/share/maven --strip-components=1 && \
    ln -s /usr/share/maven/bin/mvn /usr/bin/mvn

ENV MAVEN_HOME /usr/share/maven
ENV MAVEN_CONFIG "$USER_HOME_DIR/.m2"
ENV MAVEN_OPTS "-XX:+TieredCompilation -XX:TieredStopAtLevel=1"


WORKDIR /root
ADD https://api.github.com/repos/cmu-able/rainbow/git/refs/heads/feature/phase3 version.json
RUN git clone -b feature/phase3 --single-branch https://github.com/cmu-able/rainbow.git 
WORKDIR /root/rainbow
WORKDIR /root/rainbow/libs/auxtestlib
RUN mvn -DskipTests install
WORKDIR /root/rainbow/libs/incubator
RUN mvn -DskipTests install
WORKDIR /root/rainbow/libs/parsec
RUN mvn -DskipTests javacc:javacc install
WORKDIR /root/rainbow/libs/typelib
RUN mvn -DskipTests javacc:javacc install
WORKDIR /root/rainbow/libs/eseblib
RUN mvn -DskipTests install

WORKDIR /root/rainbow/rainbow/rainbow-core
RUN mvn -DskipTests install
WORKDIR /root/rainbow/testing
RUN mvn -DskipTests install
WORKDIR /root/rainbow/rainbow/rainbow-gui
RUN mvn -DskipTests install
WORKDIR /root/rainbow/rainbow/rainbow-acme-model
RUN mvn -DskipTests install
WORKDIR /root/rainbow/rainbow/rainbow-mem-comms
RUN mvn -DskipTests install
WORKDIR /root/rainbow/deployments/rainbow-brass
RUN mvn -DskipTests install

CMD [/bin/bash]
# Docker file for Rainbow installation

FROM cmumars/cp1_base

# Install Java
# ## per https://bugs.launchpad.net/ubuntu/+source/ca-certificates-java/+bug/1396760
#RUN sudo apt-get install -y software-properties-common

#RUN sudo apt-add-repository ppa:openjdk-r/ppa && \
#    sudo apt-get update && \

RUN sudo apt-get update && \
    sudo apt-get install -y software-properties-common openjdk-8-jre && \
    sudo /var/lib/dpkg/info/ca-certificates-java.postinst configure

WORKDIR /home/mars/catkin_ws
ADD https://api.github.com/repos/cmu-mars/ig-action-server-p15/git/refs/heads/master ig-version.json 
RUN rm -r src/ig-interpreter
RUN git clone https://github.com/cmu-mars/ig-action-server-p15.git   src/ig-interpreter 
RUN  . /opt/ros/kinetic/setup.sh && \
    catkin_make

WORKDIR /home/mars

RUN mkdir das

WORKDIR /home/mars/das

ENV PRISM_VER=4.3.1

# Install PRISM
RUN wget http://acme.able.cs.cmu.edu/public/BRASS/p2/prism-${PRISM_VER}-linux64.tar.gz && \
    tar zxf prism-${PRISM_VER}-linux64.tar.gz && \
    cd prism-${PRISM_VER}-linux64 && \
    ./install.sh && \
    echo "export LD_LIBRARY_PATH=~/das/prism-${PRISM_VER}-linux64/lib:\$LD_LIBRARY_PATH" >> ~/.bashrc && \
    cd .. && \
    rm -f prism-${PRISM_VER}-linux64.tar.gz

WORKDIR /home/mars/das
RUN mkdir rainbow-brass
WORKDIR /home/mars/das/rainbow-brass
# Install Rainbowo
COPY --from=rainbow-builder /root/rainbow/deployments/rainbow-brass/target/lib/* lib/
COPY --from=rainbow-builder /root/rainbow/deployments/rainbow-brass/target/*.jar lib/
COPY --from=rainbow-builder /root/rainbow/deployments/rainbow-brass/brass-p3-cp1 targets/brass-p3-cp1/
COPY --from=rainbow-builder /root/rainbow/scripts/*.sh ./
COPY --from=rainbow-builder /root/rainbow/scripts/log4j.properties ./
COPY brass.sh ./

RUN sudo chown -R mars /home/mars/das

RUN sudo find . -name "*.sh" -print -exec chmod a+x {} \;
RUN sudo find . -name "*.py" -print -exec chmod a+x {} \;

CMD ["/bin/bash"]
