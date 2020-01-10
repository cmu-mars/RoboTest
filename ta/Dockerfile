FROM cmumars/p3-cp1_rb

RUN . /opt/ros/kinetic/setup.sh
RUN . ~/catkin_ws/devel/setup.sh

RUN echo ". /opt/ros/kinetic/setup.bash" >> ~/.bashrc
RUN echo ". ~/catkin_ws/devel/setup.bash" >> ~/.bashrc

RUN sudo apt-get install ca-certificates
ENV GPG_KEY=0D96DF4D4110E5C43FBFB17F2D347EA6AA65421D
ENV PYTHON_VERSION=3.6.3

RUN sudo apt-get update
RUN sudo apt-get install -y ros-kinetic-gazebo-msgs awscli jq

ENV ROS_NAVIGATION_MSGS_VERSION 1.13.0
RUN wget -q "https://github.com/ros-planning/navigation_msgs/archive/${ROS_NAVIGATION_MSGS_VERSION}.tar.gz" && \
    tar -xvf "${ROS_NAVIGATION_MSGS_VERSION}.tar.gz" && \
    rm "${ROS_NAVIGATION_MSGS_VERSION}.tar.gz" && \
    mv "navigation_msgs-${ROS_NAVIGATION_MSGS_VERSION}" navigation_msgs && \
    rm navigation_msgs/README.md && \
    mv navigation_msgs/* ~/catkin_ws/src && \
    rm -rf navigation_msgs

RUN cd ~/catkin_ws && . /opt/ros/kinetic/setup.sh && catkin_make

RUN sudo mkdir -p /usr/src/app
RUN sudo chown mars /usr/src/app


WORKDIR /usr/src/app

COPY requirements.txt /usr/src/app/


RUN sudo apt-get install -y python3 python3-pip
RUN sudo pip3 install --no-cache-dir -r requirements.txt
RUN sudo pip3 install awscli --upgrade

# libs that cp1 backend depends on and since ta is running with poython3 we need them with pip3
# RUN sudo pip3 install catkin_pkg rospkg numpy psutil defusedxml flask-script

COPY . /usr/src/app
RUN sudo chown -R mars /usr/src/app
RUN python3 -m pip install /usr/src/app
ADD missions/* /home/mars/

ENV PYTHONUNBUFFERED 0

EXPOSE 8080

ADD entrypoint.sh .

ENTRYPOINT ["/usr/src/app/entrypoint.sh"]

#CMD ["python3", "-m", "swagger_server"]
