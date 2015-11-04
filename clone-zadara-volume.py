#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import logging
import logging.config
import logging.handlers

import yaml

from zadarest import ZConsoleClient
from zadarest import ZVpsaClient

logger = None

def setup_logging( log_conf=None ):
    if log_conf is None:
        logging.basicConfig( level=logging.DEBUG )
    else:
        logging.config.dictConfig( dict( log_conf ) )

    logging.info( 'start logging for %s at %s' %
            ( __name__, time.strftime( "%y%m%d-%H%M", time.localtime() ) ) )


def read_config( config_file_path ):
    with open( config_file_path, 'r' ) as ymlfile:
        config = yaml.load( ymlfile )

    # some validation of config
    if 'zadara_cloud_console' not in config.keys() or 'url' not in config['zadara_cloud_console'].keys():
            logger.critical('missing zadara CLOUD CONSOLE URL config')
            exit( 1 )
    if 'zadara_vpsa' not in config.keys() or 'volume_export_path' not in config['zadara_vpsa'].keys():
            logger.critical('missing zadara volume EXPORT PATH config')
            exit( 1 )
    if 'logging' not in config.keys():
        config['logging'] = None
    return config


def get_value_from_env_or_user_input( env_var_name, msg="enter your value: " ):
    value = None
    if env_var_name in os.environ:
        value = os.environ[ env_var_name ]
    while not value:
        value = str( raw_input( msg ) )

    return value


def setup_zadara_console_client():
    token = get_value_from_env_or_user_input(
            'ZADARA_CONSOLE_ACCESS_TOKEN',
            'enter your zadara CONSOLE access token: ' )
    zcon = ZConsoleClient( cfg['zadara_cloud_console']['url'], token )

    logger.debug('set zconsole for url(%s)' % cfg['zadara_cloud_console']['url'] )
    logger.debug('zconsole object is (%s)' % zcon )
    return zcon


def setup_zadara_vpsa_client( z_console_client, vpsa_id ):
    token = get_value_from_env_or_user_input(
            'ZADARA_VPSA_ACCESS_TOKEN',
            'enter your zadara VPSA token: ' )
    zvpsa = ZVpsaClient( z_console_client, vpsa_token=token, vpsa_id=vpsa_id )

    logger.debug('set zvpsa for id (%d)' % vpsa_id )
    logger.debug('zvpsa object is (%s)' % zvpsa )
    return zvpsa


def setup_zadara_client():
    zcon = setup_zadara_console_client()

    vpsa_token = get_value_from_env_or_user_input(
            'ZADARA_VPSA_ACCESS_TOKEN',
            'enter your zadara VPSA token: ' )
    os.environ['ZADARA_VPSA_ACCESS_TOKEN'] = vpsa_token

    vpsa = zcon.vpsa_by_export_path( cfg['zadara_vpsa']['volume_export_path'], vpsa_token )
    if vpsa is None:
        logger.critical(
                'vpsa with export_path(%s) not found; maybe it is hibernated?' %
                    cfg['zadara_vpsa']['volume_export_path'] )
        exit( 1 )

    logger.debug('found vpsa with export_path (%s)! it has id (%d)' % (
        cfg['zadara_vpsa']['volume_export_path'], vpsa['id']) )

    zcli = setup_zadara_vpsa_client( zcon, vpsa['id'] )
    return zcli


def print_snapshot_list_from_volume( cli, volume ):
    snapshots = {}
    snap_list = cli.get_snapshots_for_cgroup( volume['cg_name'] )

    if snap_list is None or 0 == len( snap_list ):
        logger.critical(
                'no snapshots available for volume with export_path(%s)' %
                    volume['nfs_export_path'] )
        exit( 1 )

    logger.debug('return from snapshot list has (%d) elements' % len( snap_list ) )

    i = 1
    print 'available snapshots for volume with export_path(%s):' % volume['nfs_export_path']
    for s in snap_list:
        print '%d: %s [%s]' % ( i, s['modified_at'], s['display_name'] )
        snapshots[i] = s
        i += 1

    return snapshots


def clone_from_snapshot( cli, volume, snapshot_id ):
    timestamp = time.strftime( "%y%m%d_%H%M", time.localtime() )
    #clone_volume_display_name = 'clone_snap_%s_on_%s' % ( snapshot_id.replace('-', '_'), timestamp )
    clone_volume_display_name = 'clone_on_%s' % timestamp

    logger.debug( 'cloning volume (%s) with display_name (%s), from snapshot_id (%s)' %
            ( volume['cg_name'], clone_volume_display_name, snapshot_id ) )

    clone = cli.clone_volume(
            cgroup=volume['cg_name'],
            clone_name=clone_volume_display_name,
            snap_id=snapshot_id )

    timeout_in_sec = 5
    max_checks = 5
    i = 0
    while clone is None and i < max_checks:
        time.sleep( timeout_in_sec )
        clone = cli.get_volume_by_display_name( clone_volume_display_name )
        i += 1

    if i == max_checks and clone is None:
        logger.critical('error cloning volume')
        exit( 1 )

    logger.debug( 'cloned volume object is (%s)' % clone )

    return clone


def shift_export_paths( cli, source_volume, clone_volume ):
    timestamp = time.strftime( "%y%m%d-%H%M", time.localtime() )
    de_facto_export_path = source_volume['nfs_export_path']
    inactive_export_path = '%s_%s' % ( source_volume['nfs_export_path'], timestamp )

    logger.debug('preparing to shift export paths: (%s)-->(%s)-->X(%s)' %
        ( inactive_export_path, de_facto_export_path, clone_volume['nfs_export_path'] ) )

    src_servers = cli.detach_volume_from_all_servers( source_volume['name'] )
    src_volume_name = cli.update_export_name_for_volume(
            source_volume['name'],
            os.path.basename( inactive_export_path ) )

    logger.debug('detached source_volume from all servers (%s)' % src_servers )

    clone_volume_name = cli.update_export_name_for_volume(
            clone_volume['name'],
            os.path.basename( de_facto_export_path ) )
    clone_servers = cli.attach_volume_to_servers( clone_volume['name'], src_servers )

    logger.debug('attached all servers to clone volume (%s)' % clone_servers )
    logger.debug('src_volume_name(%s) and clone_volume_name(%s)' % ( src_volume_name,
        clone_volume_name ) )

    return ( src_volume_name, clone_volume_name )


def copy_snapshot_policies( cli, source_volume, clone_volume ):
    src_policies = cli.get_snapshot_policies_for_cgroup( source_volume['cg_name'] )

    logger.debug('policies from src_volume (%s)' % src_policies )

    for p in src_policies:
        cli.attach_snapshot_policy_to_cgroup( clone_volume['cg_name'], p['name'] )

    logger.debug('policies now attached to clone_volume as well...')

    return src_policies



if __name__ == '__main__':
    cfg = read_config( 'config.yml' )
    setup_logging( cfg['logging'] )

    logger = logging.getLogger( __name__ )
    logger.info('STEP 1. logging configured!')
    logger.info('STEP 2. setting up zadara client...')

    zcli = setup_zadara_client()

    logger.info('STEP 3. finding volume to be clone by export_path (%s)' %
            cfg['zadara_vpsa']['volume_export_path'])

    volume_to_clone_info = zcli.get_volume_by_export_path( cfg['zadara_vpsa']['volume_export_path'] )

    logger.info('STEP 4. volume found (%s); printing snapshots available',
            volume_to_clone_info['display_name'] )

    snapshots = print_snapshot_list_from_volume( zcli, volume_to_clone_info )
    s_index = None
    while not s_index and s_index not in snapshots.keys():
        s_index = int( raw_input('which snapshot to clone? [1..%d]: ' % len( snapshots ) ) )

    logger.info('STEP 5. snapshot picked (%s), cloning...' % snapshots[ s_index
            ]['display_name'] )

    clone_info = clone_from_snapshot(
        zcli,
        volume_to_clone_info,
        snapshots[ s_index ]['name'] )

    logger.info('STEP 6. cloned as volume (%s); changing export_paths...' %
            clone_info['display_name'] )

    ( src_path, clone_path ) = shift_export_paths(
        zcli,
        volume_to_clone_info,
        clone_info )

    logger.info('STEP 7. attaching snapshot policies...')

    p_list = copy_snapshot_policies(
        zcli,
        volume_to_clone_info,
        clone_info )

    logger.info('STEP 8. remount shared storage in mh nodes and we are done.')





