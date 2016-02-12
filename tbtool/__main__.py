#!/usr/bin/env python

from docopt import docopt
import os, textwrap, uuid, datetime, getpass, shutil
import subprocess
from .appdirs import AppDirs


def tingbot_key_path():
    dir_path = '/tmp/tide-key-%s/' % getpass.getuser()
    tmp_path = os.path.join(dir_path, 'tingbot.key')

    if not os.path.exists(tmp_path):
        if not os.path.exists(dir_path):
            os.mkdir(os.path.dirname(tmp_path), 0700)
        src_path = os.path.join(os.path.dirname(__file__), 'tingbot.key')
        shutil.copyfile(src_path, tmp_path)
        os.chmod(tmp_path, 0600)

    return tmp_path


def open_ssh_session(hostname):
    control_path = '/tmp/tide-ssh-control-{uuid}-{t.hour}:{t.minute}'.format(
        uuid=uuid.uuid1(),
        t=datetime.datetime.now())

    subprocess.check_call([
        'ssh',
        '-nNf4',
        '-o', 'UserKnownHostsFile=/dev/null',
        '-o', 'StrictHostKeyChecking=no',
        '-i', tingbot_key_path(),
        '-o', 'ControlMaster=yes',
        '-o', 'ControlPath=%s' % control_path,
        'pi@%s' % hostname])

    return control_path


def close_ssh_session(control_path):
    subprocess.check_call([
        'ssh',
        '-o', 'ControlPath=%s' % control_path,
        '-O', 'exit',
        'hostname-not-required'])


def simulate(app_path):
    python_exe = install_deps(app_path)

    main_file = os.path.abspath(os.path.join(app_path, 'main'))

    os.chdir(app_path)

    if os.path.exists(main_file):
        os.execvp(main_file, [main_file])
    else:
        os.execvp(python_exe, [python_exe, 'main.py'])


def run(app_path, hostname):
    print 'Connecting to Pi...'

    control_path = open_ssh_session(hostname)

    try:
        app_name = os.path.basename(app_path)

        app_install_location = '/tmp/tide/%s' % app_name
        app_install_folder = os.path.dirname(app_install_location)

        print 'Setting up Pi...'

        subprocess.check_call([
            'ssh',
            '-o', 'ControlPath=%s' % control_path,
            'pi@%s' % hostname,
            'mkdir -p %s' % app_install_folder])

        print 'Copying app to %s...' % app_install_location

        subprocess.check_call([
            'rsync',
            '--recursive',
            '--perms',
            '--links', '--safe-links',
            '--delete',
            '-e', 'ssh -o ControlPath=%s' % control_path,
            app_path + '/',
            'pi@%s:"%s"' % (hostname, app_install_location)])

        print 'Starting app...'

        subprocess.check_call([
            'ssh',
            '-o', 'ControlPath=%s' % control_path,
            'pi@%s' % hostname,
            'tbopen --follow "%s"' % app_install_location])
    finally:
        close_ssh_session(control_path)


def install_deps(app_path):
    '''
    Installs the dependencies in requirements.txt into a virtualenv in the app directory
    Returns the path to the python executable that should be used to run the app.
    '''
    import virtualenv
    wheelhouse = os.path.join(AppDirs('Tingbot', 'Tingbot').user_cache_dir, 'Wheelhouse')

    if not os.path.exists(wheelhouse):
        os.makedirs(wheelhouse)

    requirements_txt_path = os.path.join(app_path, 'requirements.txt')
    venv_path = os.path.join(app_path, 'venv')
    venv_bin_dir = virtualenv.path_locations(venv_path)[3]
    venv_python_path = os.path.join(venv_bin_dir, 'python')

    if not os.path.exists(requirements_txt_path):
        # make sure there's no venv and exit
        shutil.rmtree(venv_path, ignore_errors=True)
        return 'python'

    # check that there's a virtualenv there and that it's got a working
    # version of python
    try:
        subprocess.check_call([
            venv_python_path,
            '-c', 'import sys; sys.exit(0)'
        ])
    except (OSError, subprocess.CalledProcessError):
        # we've got to build the virtualenv
        shutil.rmtree(venv_path, ignore_errors=True)

        virtualenv.create_environment(venv_path, site_packages=True,)

    venv_pip_path = os.path.join(venv_bin_dir, 'pip')

    env = os.environ.copy()
    env['PIP_FIND_LINKS'] = 'file://%s' % wheelhouse
    env['PIP_WHEEL_DIR'] = wheelhouse

    subprocess.check_call([
            venv_pip_path,
            'install', '-r', requirements_txt_path,
        ],
        env=env
    )

    return venv_python_path

def install(app_path, hostname):
    control_path = open_ssh_session(hostname)

    try:
        app_name = os.path.basename(app_path)

        app_install_location = '/apps/%s' % app_name

        subprocess.check_call([
            'rsync',
            '--recursive',
            '--perms',
            '--links', '--safe-links',
            '--delete',
            '-e', 'ssh -o ControlPath=%s' % control_path,
            app_path,
            'pi@%s:%s' % (hostname, app_install_location)])

        subprocess.check_call([
            'ssh',
            '-o', 'ControlPath=%s' % control_path,
            'pi@%s' % hostname,
            'tbopen /apps/home'])
    finally:
        close_ssh_session(control_path)


def main():
    args = docopt(textwrap.dedent('''
        Usage: tbtool simulate <app>
               tbtool run <app> <hostname>
               tbtool install <app> <hostname>
        '''))

    # simulate: Runs an app in the tingbot simulator (must be a python app).
    # run: Runs an app on the tingbot specified by <hostname>, without installing.
    # install: Installs an app on the tingbot specified

    if args['simulate']:
        return simulate(args['<app>'])
    elif args['run']:
        return run(args['<app>'], args['<hostname>'])
    elif args['install']:
        return install(args['<app>'], args['<hostname>'])

if __name__ == '__main__':
    main()
