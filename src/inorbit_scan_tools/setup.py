from setuptools import setup
from glob import glob

package_name = 'inorbit_scan_tools'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Your Name',
    maintainer_email='argen1swong@gmail.com',
    description='Tools to adapt lidar scans for InOrbit visualization.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'scan_frame_republisher = inorbit_scan_tools.scan_frame_republisher:main',
            'initial_pose_publisher = inorbit_scan_tools.initial_pose_publisher:main',
            'waypoint_mission = inorbit_scan_tools.waypoint_mission:main',
        ],
    },
)
