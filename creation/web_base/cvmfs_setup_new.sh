#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2009 Fermi Research Alliance, LLC
# SPDX-License-Identifier: Apache-2.0

determine_cvmfsexec_mode_usage() {
    if [[ $GWMS_IS_UNPRIV_USERNS_SUPPORTED && $GWMS_IS_UNPRIV_USERNS_ENABLED && $GWMS_IS_FUSERMOUNT ]]; then
        if [[ $GWMS_OS_KRNL_VER -ge 4 && $GWMS_OS_KRNL_MAJOR_REV -ge 18 || $GWMS_OS_KRNL_VER -ge 3 && $GWMS_OS_KRNL_MAJOR_REV -ge 10 && $GWMS_OS_KRNL_MINOR_REV -ge 0 && $GWMS_OS_KRNL_PATCH_NUM -ge 1127 ]]; then
            # echo "cvmfsexec mode 3 can be used"
            echo 3     # true
        else
            # echo "Mode 3 of cvmfsexec unavailable; use mode 2 of cvmfsexec instead"
            echo 2     # false
        fi
    else
        # echo "Usernamespaces and/or fuse mounts not available in unprivileged mode. Defaulting to mode 2 of cvmfsexec"
        echo 2         # false
    fi
}

is_cvmfs_needed() {
    # get the cvmfsexec attribute switch value from the config file
    [[ -e "$1" ]] && use_cvmfsexec="$(grep '^GLIDEIN_USE_CVMFSEXEC ' "$glidein_config" | awk '{print $2}')"
    # TODO: change this variable to 'GLIDEIN_CVMFS' [convention for external variables]
    # TODO: when changed, the GLIDEIN_CVMFS variable takes on possible values from {required, preferred, optional, never}
    # TODO: int or string?? if string, make the attribute value case insensitive
    #use_cvmfsexec=${use_cvmfsexec,,}
    # echo "use_cvmfsexec is set to $use_cvmfsexec"

    if [[ $use_cvmfsexec -ne 1 ]]; then
        "$error_gen" -ok "$(basename $0)" "msg" "Not using cvmfsexec; skipping setup."
        exit 0
    fi

    true
}

is_cvmfs_locally_mounted() {
    variables_reset

    detect_local_cvmfs

    # check if CVMFS is already locally mounted...
    if [[ $GWMS_IS_CVMFS_MNT -eq 0 ]]; then
        # if it is so...
        echo "in here..."
        "$error_gen" -ok "$(basename $0)" "msg" "CVMFS is locally mounted on the node; skipping setup using cvmfsexec utilities."
        exit 0
    fi

    echo "CVMFS is not found locally on the worker node..."
    false
}

setup_for_cvmfsexec() {
    echo "*** inside setup_for_cvmfsexec function... ***"
    # # import add_config_line function
    # [[ -e "$glidein_config" ]] && add_config_line_source="$(grep '^ADD_CONFIG_LINE_SOURCE ' "$glidein_config" | awk '{print $2}')"
    # echo "add_config_line_source is set to $add_config_line_source"
    # # echo "add_config_line_source=$add_config_line_source" >> "$temp_file"
    # # shellcheck source=./add_config_line.source
    # . $add_config_line_source

    gwms_cvmfsexec_mode=$(determine_cvmfsexec_mode_usage)
    if [[ $gwms_cvmfsexec_mode -eq 3 ]]; then
        echo "cvmfsexec can be used in mode 3"
    elif [[ $gwms_cvmfsexec_mode -eq 2 ]]; then
        echo "cvmfsexec will be used in mode 2 only"
    else
        echo "invalid value for GWMS_CVMFSEXEC_MODE"
    fi

    # TODO: update to gconfig_add
    add_config_line GWMS_CVMFSEXEC_MODE $gwms_cvmfsexec_mode
    # echo "gwms_cvmfsexec_mode=$gwms_cvmfsexec_mode" >> "$temp_file"
}

################################################################################
#
# All code out here will run on the 1st invocation (whether Singularity is wanted or not)
# and also in the re-invocation within Singularity
# $HAS_SINGLARITY is used to discriminate if Singularity is desired (is 1) or not
# $GWMS_SINGULARITY_REEXEC is used to discriminate the re-execution (nothing outside, 1 inside)
#

# script_to_invoke=$1
# glidein_config=$2
# entry_id=$3

# echo "*****************************************************"
# echo "$@"     # gives glidein_config main as the result since it is with respect to this script
# echo "*****************************************************"

GWMS_THIS_SCRIPT="$0"
# echo "GWMS_THIS_SCRIPT is set to $GWMS_THIS_SCRIPT"
GWMS_THIS_SCRIPT_DIR=$(dirname "$0")
# echo "GWMS_THIS_SCRIPT_DIR is set to $GWMS_THIS_SCRIPT_DIR"
echo "The new cvmfs_setup script is being picked and recognized during the factory upgrade"

# first parameter passed to this script will always be the glidein configuration file (glidein_config)
glidein_config=$1

# import add_config_line function
add_config_line_source=$(grep -m1 '^ADD_CONFIG_LINE_SOURCE ' "$glidein_config" | cut -d ' ' -f 2-)
source "$add_config_line_source"

[[ -e "$glidein_config" ]] && error_gen=$(gconfig_get ERROR_GEN_PATH "$glidein_config")

if [[ -e "$GWMS_THIS_SCRIPT_DIR/cvmfs_helper_funcs.sh" ]]; then
    CVMFS_AUX_DIR="$GWMS_THIS_SCRIPT_DIR"
# else
#     warn_raw "ERROR: $GWMS_THIS_SCRIPT: Unable to source singularity_lib.sh! File not found. Quitting"
#     exit_wrapper "Wrapper script $GWMS_THIS_SCRIPT failed: Unable to source singularity_lib.sh" 1
fi
# shellcheck source=./singularity_lib.sh
. "${CVMFS_AUX_DIR}"/cvmfs_helper_funcs.sh

# if GLIDEIN_USE_CVMFSEXEC is set to 1 - check if CVMFS is locally available in the node
# validate CVMFS by examining the directories within CVMFS... checking just one directory should be sufficient?
# get the glidein work directory location from glidein_config file
[[ -e "$glidein_config" ]] && work_dir=$(gconfig_get GLIDEIN_WORK_DIR "$glidein_config")
# $PWD=/tmp/glide_xxx and every path is referenced with respect to $PWD
echo "work_dir set to $work_dir"

# ################################# main #################################
echo "Checking for the value of GWMS_CVMFS_REEXEC..."
echo "GWMS_CVMFS_REEXEC set to $GWMS_CVMFS_REEXEC"
if [[ -z $GWMS_CVMFS_REEXEC ]]; then
    # run this block only on the first invocation of this script
    echo "in the first if condition..."
    loginfo "first invocation of the script for cvmfsexec"

    if is_cvmfs_needed "$glidein_config" ; then
    # echo "cvmfs_needed $?"
        echo "CVMFS IS NEEDED! back in the main script... continuing to run"
        if ! is_cvmfs_locally_mounted ; then
        # echo "cvmfs_mounted $?"
            echo "Proceeding with setting up cvmfsexec..."
        fi

        perform_system_check

        setup_for_cvmfsexec

        # [[ -e glidein_config ]] && gwms_cvmfsexec_mode="$(grep '^GWMS_CVMFSEXEC_MODE ' "$glidein_config" | awk '{print $2}')"
        # echo "gwms_cvmfsexec_mode set to $gwms_cvmfsexec_mode"

        # before exiting out of this block, do two things...
        # one, set a variable indicating this script has been executed once
        gwms_cvmfs_reexec=yes
        # TODO: update to gconfig_add
        add_config_line GWMS_CVMFS_REEXEC $gwms_cvmfs_reexec
        echo "GWMS_CVMFS_REEXEC in glidein_config set to $gwms_cvmfs_reexec"

        # two, export required variables before reinvoking glidein_start_up again...
        # reinvoke_script=$(ps $PPID | tail -n 1 | awk "{print \$6}")
        ps $PPID
        #ps $PPID | awk '{print \$(NF)}'
        # echo "reinvoke_script set to $reinvoke_script"

        # $glidein_cvmfsexec_dir/$dist_file $GLIDEIN_CVMFS_CONFIG_REPO -- $reinvoke_script $REINVOCATION_ARGS
        # $glidein_cvmfsexec_dir/$dist_file $GLIDEIN_CVMFS_CONFIG_REPO -- echo "Running script inside the cvmfsexec environment..."
        # export the required variables before calling the glidein_startup script the second time
        # check if it is the second time the script is being called
        # if yes, import the variables that were created during the first invocation (e.g. work_dir)
        # only need to focus on global variables and not local ones for my work on cvmfsexec

        # suggestion by Marco -- enclose the cvmfsexec command inside of parantheses
        # having a function that has all the cvmfsexec function; $1 - first input to the function
        # awaiting from Bruno for the cvmfsexec line from the Wilson Cluster project

    elif [[ $gwms_cvmfsexec_mode -eq 2 ]]; then
        echo "using mode 2 cvmfsexec..."
    else
        echo "Invalid value!"
    fi
fi
