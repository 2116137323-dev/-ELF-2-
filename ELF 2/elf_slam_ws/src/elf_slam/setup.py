from setuptools import setup
import os
from glob import glob
import shutil
import stat
import subprocess

package_name = 'elf_slam'


def resolve_encoder_paths():
    """colcon 会在 build/elf_slam 下执行 setup.py，需回退到源码目录找 .c 文件。"""
    here = os.path.dirname(os.path.abspath(__file__))
    source_candidates = [
        os.path.join(here, 'src', 'encoder_raw.c'),
        os.path.join(here, '..', '..', 'src', package_name, 'src', 'encoder_raw.c'),
    ]
    for candidate in source_candidates:
        resolved = os.path.normpath(os.path.abspath(candidate))
        if os.path.exists(resolved):
            return resolved, os.path.join(here, 'scripts', 'encoder_raw')
    return None, os.path.join(here, 'scripts', 'encoder_raw')


def build_encoder_raw():
    if os.name == 'nt':
        return None

    encoder_source, encoder_target = resolve_encoder_paths()
    if encoder_source is None:
        print(
            'WARNING: encoder_raw.c not found; skipping encoder binary build. '
            'encoder_bridge will still publish odom TF without wheel pulses.'
        )
        return None

    compiler = shutil.which('gcc')
    if compiler is None:
        print('WARNING: gcc not found; skipping encoder_raw build.')
        return None

    source_mtime = os.path.getmtime(encoder_source)
    target_mtime = os.path.getmtime(encoder_target) if os.path.exists(encoder_target) else 0
    if target_mtime >= source_mtime:
        return encoder_target

    os.makedirs(os.path.dirname(encoder_target), exist_ok=True)
    subprocess.check_call([
        compiler,
        encoder_source,
        '-O2',
        '-o',
        encoder_target,
    ])
    os.chmod(
        encoder_target,
        os.stat(encoder_target).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
    )
    return encoder_target


encoder_binary = build_encoder_raw()
package_dir = os.path.dirname(os.path.abspath(__file__))

data_files = [
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    ('share/' + package_name, ['package.xml']),
    (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
    (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
    (os.path.join('share', package_name, 'config'), glob('config/*.rviz')),
    (os.path.join('share', package_name, 'urdf'), glob('urdf/*.urdf')),
    (os.path.join('share', package_name, 'scripts'), glob('scripts/*.sh')),
]

if encoder_binary and os.path.exists(encoder_binary):
    rel_binary = os.path.relpath(encoder_binary, package_dir)
    data_files.append(('lib/' + package_name, [rel_binary]))

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=data_files,
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='elf',
    maintainer_email='elf@todo.todo',
    description='ELF Robot SLAM package',
    license='TODO: License declaration',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'encoder_bridge = elf_slam.encoder_bridge:main',
            'scan_stamp_fix = elf_slam.scan_stamp_fix:main',
            'diff_drive_controller = elf_slam.diff_drive_controller:main',
            'robot_description_publisher = elf_slam.robot_description_publisher:main',
        ],
    },
)
