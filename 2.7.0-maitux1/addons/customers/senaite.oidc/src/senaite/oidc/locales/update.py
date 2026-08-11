# -*- coding: utf-8 -*-

import os
import pkg_resources
import subprocess


domain = 'senaite.oidc'
os.chdir(pkg_resources.resource_filename(domain, ''))
os.chdir('../../../')
target_path = 'src/senaite/oidc/'
locale_path = target_path + 'locales/'
i18ndude = './bin/i18ndude'

# ignore node_modules files resulting in errors
excludes = '"*.html *json-schema*.xml"'


def locale_folder_setup():
    os.chdir(locale_path)
    languages = [d for d in os.listdir('.') if os.path.isdir(d)]
    for lang in languages:
        folder = os.listdir(lang)
        if 'LC_MESSAGES' in folder:
            continue
        else:
            lc_messages_path = lang + '/LC_MESSAGES/'
            os.mkdir(lc_messages_path)
            cmd = 'msginit --locale={0} --input={1}.pot --output={2}/LC_MESSAGES/{3}.po'.format(  # NOQA: E501
                lang,
                domain,
                lang,
                domain,
            )
            subprocess.call(
                cmd,
                shell=True,
            )

    os.chdir('../../../../')


def _rebuild():
    cmd = '{i18ndude} rebuild-pot --pot {locale_path}/{domain}.pot --exclude {excludes} --create {domain} {target_path}'.format(  # NOQA: E501
        i18ndude=i18ndude,
        locale_path=locale_path,
        domain=domain,
        target_path=target_path,
        excludes=excludes,
    )
    subprocess.call(
        cmd,
        shell=True,
    )


def _sync():
    cmd = '{0} sync --pot {1}/{2}.pot {3}*/LC_MESSAGES/{4}.po'.format(
        i18ndude,
        locale_path,
        domain,
        locale_path,
        domain,
    )
    subprocess.call(
        cmd,
        shell=True,
    )


def update_locale():
    locale_folder_setup()
    _sync()
    _rebuild()
