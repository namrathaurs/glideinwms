#!/bin/bash

# SPDX-FileCopyrightText: 2009 Fermi Research Alliance, LLC
# SPDX-License-Identifier: Apache-2.0

# Project:
#	GlideinWMS
#
#
# Description:
#	This script contains helper functions that support the mount/unmount of
#	CVMFS on worker nodes.
#
#
# Used by:
#	cvmfs_setup.sh, cvmfs_unmount.sh
#
# Author:
#	Namratha Urs
#


# to implement custom logging
# https://stackoverflow.com/questions/42403558/how-do-i-manage-log-verbosity-inside-a-shell-script
# WORKAROUND: redirect stdout and stderr to some file
#LOGFILE="cvmfs_all.log"
#exec &> $LOGFILE

variables_reset() {
    # DESCRIPTION: This function lists and initializes the common variables
    # to empty strings. These variables also become available to scripts
    # that import functions defined in this script.
    #
    # INPUT(S): None
    # RETURN(S): Variables initialized to empty strings

    # indicates whether the perform_system_check function has been run
    GWMS_SYSTEM_CHECK=

    # following set of variables used to store operating system and kernel info
    GWMS_OS_DISTRO=
    GWMS_OS_NAME=
    GWMS_OS_VERSION_FULL=
    GWMS_OS_VERSION_MAJOR=
    GWMS_OS_VERSION_MINOR=
    GWMS_OS_KRNL_ARCH=
    GWMS_OS_KRNL_NUM=
    GWMS_OS_KRNL_VER=
    GWMS_OS_KRNL_MAJOR_REV=
    GWMS_OS_KRNL_MINOR_REV=
    GWMS_OS_KRNL_PATCH_NUM=

    # indicates whether CVMFS is locally mounted on the worker node (CE)
    GWMS_IS_CVMFS_LOCAL_MNT=
    # to indicate the status of on-demand mounting of CVMFS by the glidein after evaluating the worker node (CE)
    GWMS_IS_CVMFS=

    # indicates if unpriv userns is available (or supported); not if it is enabled
    GWMS_IS_UNPRIV_USERNS_SUPPORTED=
    # indicates if unpriv userns is enabled (and available)
    GWMS_IS_UNPRIV_USERNS_ENABLED=

    # following variables store FUSE-related information
    GWMS_IS_FUSE_INSTALLED=
    GWMS_IS_FUSERMOUNT=
    GWMS_IS_USR_IN_FUSE_GRP=
}


loginfo() {
    # DESCRIPTION: This function prints informational messages to STDOUT
    # along with hostname and date/time.
    #
    # INPUT(S): String containing the message
    # RETURN(S): Prints message to STDOUT

    echo -e "$(date +%m-%d-%Y\ %T\ %Z) \t INFO: $1" >&2
}


logwarn(){
    # DESCRIPTION: This function prints warning messages to STDOUT along
    # with hostname and date/time.
    #
    # INPUT(S): String containing the message
    # RETURN(S): Prints message to STDOUT

    echo -e "$(date +%m-%d-%Y\ %T\ %Z) \t WARNING: $1" >&2
}


logerror() {
    # DESCRIPTION: This function prints error messages to STDOUT along with
    # hostname and date/time.
    #
    # INPUT(S): String containing the message
    # RETURN(S): Prints message to STDOUT

    echo -e "$(date +%m-%d-%Y\ %T\ %Z) \t ERROR: $1" >&2
}


print_exit_status () {
    # DESCRIPTION: This function prints an appropriate message to the
    # console to indicate what the exit status means.
    #
    # INPUT(S): Number (exit status of a previously run command)
    # RETURN(S): Prints "yes" or "no" to indicate the result of the command

    [[ $1 -eq 0 ]] && echo yes || echo no
}


detect_local_cvmfs() {
    # DESCRIPTION: This function detects whether CVMFS is natively (aka locally) available on the worker node. The result is stored in a common variable, i.e. GWMS_IS_CVMFS_LOCAL_MNT, and can be used downstream.
    #
    # INPUT(S): None
    # RETURN(S): None

    CVMFS_ROOT="/cvmfs"
    repo_name=oasis.opensciencegrid.org
    # Second check...
    GWMS_IS_CVMFS_LOCAL_MNT=0
    if [[ -f $CVMFS_ROOT/$repo_name/.cvmfsdirtab || "$(ls -A $CVMFS_ROOT/$repo_name)" ]] &>/dev/null
    then
        loginfo "Validating CVMFS with ${repo_name}..."
    else
        logwarn "Validating CVMFS with ${repo_name}: directory empty or does not have .cvmfsdirtab"
        GWMS_IS_CVMFS_LOCAL_MNT=1
    fi

    loginfo "Worker node has native CVMFS: $(print_exit_status $GWMS_IS_CVMFS_LOCAL_MNT)"
}


perform_system_check() {
    # DESCRIPTION: This functions performs required system checks (such as
    # operating system and kernel info, unprivileged user namespaces, FUSE
    # status) and stores the results in the common variables for later use.
    #
    # INPUT(S): None
    # RETURN(S):
    # 	-> common variables containing the exit status of the
    # 	corresponding commands
    # 	-> results from running the print_exit_status function
    # 	for logging purposes (variables starting with res_)
    # 	-> assigns "yes" to GWMS_SYSTEM_CHECK to indicate this function
    # 	has been run.

    # reset all variables used in this script's namespace before executing the rest of the script
    # variables_reset

    # local user_namespaces
    if [[ -f '/etc/redhat-release' ]]; then
        # rhel derivative; use /etc/redhat-release to fetch the release information
        # NOTE: using /etc/redhat-release over /etc/os-release as it is more consistent to rely on
        GWMS_OS_DISTRO="rhel"
        # GWMS_OS_DISTRO="non-rhel"
        #GWMS_OS_VERSION_FULL=$(cat /etc/redhat-release | cut -d " " -f 3)
        else
        # not a rhel derivative; use /etc/os-release instead [fallback option]
        GWMS_OS_DISTRO="non-rhel"
        #GWMS_OS_VERSION_FULL=$(cat /etc/os-release | egrep "VERSION_ID" | cut -d = -f 2 | tr -d '"')
    fi

    # source the os-release file to access the variables defined
    . /etc/os-release
    GWMS_OS_VERSION_FULL=$VERSION_ID
    GWMS_OS_VERSION_MAJOR=$(echo "$GWMS_OS_VERSION_FULL" | awk -F'.' '{print $1}')
    GWMS_OS_VERSION_MINOR=$(echo "$GWMS_OS_VERSION_FULL" | awk -F'.' '{print $2}')
    GWMS_OS_NAME=${NAME,,}
    GWMS_OS_KRNL_ARCH=$(arch)
    GWMS_OS_KRNL_NUM=$(uname -r | awk -F'-' '{split($2,a,"."); print $1,a[1]}' | cut -f 1 -d " " )
    GWMS_OS_KRNL_VER=$(uname -r | awk -F'-' '{split($2,a,"."); print $1,a[1]}' | cut -f 1 -d " " | awk -F'.' '{print $1}')
    GWMS_OS_KRNL_MAJOR_REV=$(uname -r | awk -F'-' '{split($2,a,"."); print $1,a[1]}' | cut -f 1 -d " " | awk -F'.' '{print $2}')
    GWMS_OS_KRNL_MINOR_REV=$(uname -r | awk -F'-' '{split($2,a,"."); print $1,a[1]}' | cut -f 1 -d " " | awk -F'.' '{print $3}')
    GWMS_OS_KRNL_PATCH_NUM=$(uname -r | awk -F'-' '{split($2,a,"."); print $1,a[1]}' | cut -f 2 -d " ")

    # call function to detect local CVMFS only if the GWMS_IS_CVMFS_LOCAL_MNT variable is not set; if the variable is not empty, do nothing
    [[ -z "${GWMS_IS_CVMFS_LOCAL_MNT}" ]] && detect_local_cvmfs || :

    cat /proc/sys/user/max_user_namespaces &>/dev/null
    GWMS_IS_UNPRIV_USERNS_SUPPORTED=$?

    unshare -U true &>/dev/null
    GWMS_IS_UNPRIV_USERNS_ENABLED=$?

    [[ $GWMS_OS_VERSION_MAJOR -ge 9 ]] && dnf list installed fuse3* &>/dev/null || yum list installed fuse &>/dev/null
    GWMS_IS_FUSE_INSTALLED=$?
    
    [[ $GWMS_OS_VERSION_MAJOR -ge 9 ]] && fusermount3 -V &>/dev/null || fusermount -V &>/dev/null
    GWMS_IS_FUSERMOUNT=$?

    getent group fuse | grep $USER &>/dev/null
    GWMS_IS_USR_IN_FUSE_GRP=$?

    # set the variable indicating this function has been run
    GWMS_SYSTEM_CHECK=yes
}


print_os_info () {
    # DESCRIPTION: This functions prints operating system and kernel
    # information to STDOUT.
    #
    # INPUT(S): None
    # RETURN(S): Prints a message containing OS and kernel details

    loginfo "Found $GWMS_OS_NAME [$GWMS_OS_DISTRO] ${GWMS_OS_VERSION_FULL}-${GWMS_OS_KRNL_ARCH} with kernel $GWMS_OS_KRNL_NUM-$GWMS_OS_KRNL_PATCH_NUM"
}


log_all_system_info () {
    # DESCRIPTION: This function prints all the necessary system information
    # stored in common and result variables (see perform_system_check
    # function) for easy debugging. This has been done as collecting
    # information about the worker node can be useful for troubleshooting
    # and gathering stats about what is out there.
    #
    # INPUT(S): None
    # RETURN(S): Prints user-friendly messages to STDOUT

    # make sure that perform_system_check has run
    [[ -z "${GWMS_SYSTEM_CHECK}" ]] && perform_system_check
    print_os_info
    loginfo "..."
    loginfo "Worker node details: "
    loginfo "Hostname: $(hostname)"
    loginfo "Operating system distro: $GWMS_OS_DISTRO"
    loginfo "Operating system name: $GWMS_OS_NAME"
    loginfo "Operating system version: $GWMS_OS_VERSION_FULL"
    loginfo "Kernel architecture: $GWMS_OS_KRNL_ARCH"
    loginfo "Kernel version: $GWMS_OS_KRNL_VER"
    loginfo "Kernel major revision: $GWMS_OS_KRNL_MAJOR_REV"
    loginfo "Kernel minor revision: $GWMS_OS_KRNL_MINOR_REV"
    loginfo "Kernel patch number: $GWMS_OS_KRNL_PATCH_NUM"

    loginfo "CVMFS locally installed: $(print_exit_status $GWMS_IS_CVMFS_LOCAL_MNT)"
    loginfo "Unprivileged user namespaces supported: $(print_exit_status $GWMS_IS_UNPRIV_USERNS_SUPPORTED)"
    loginfo "Unprivileged user namespaces enabled: $(print_exit_status $GWMS_IS_UNPRIV_USERNS_ENABLED)"
    loginfo "FUSE installed: $(print_exit_status $GWMS_IS_FUSE_INSTALLED)"
    loginfo "fusermount available: $(print_exit_status $GWMS_IS_FUSERMOUNT)"
    loginfo "Is the user in 'fuse' group: $(print_exit_status $GWMS_IS_USR_IN_FUSE_GRP)"
    loginfo "..."
}


mount_cvmfs_repos () {
    # DESCRIPTION: This function mounts all the required and additional
    # CVMFS repositories that would be needed for user jobs.
    #
    # INPUT(S):
    #    1. cvmfsexec mode (integer)
    #    2. CVMFS configuration repository (string)
    #    3. Additional CVMFS repositories (colon-delimited string)
    # RETURN(S): Mounts the defined repositories on the worker node filesystem
    local cvmfsexec_mode=$1
    local config_repository=$2
    local additional_repos=$3
    local config_repo_mntd num_repos_mntd total_num_repos

    # if using mode 3, config repo should have been mounted already
    # otherwise if using mode 1, mount the config repo now...
    if [[ $cvmfsexec_mode -eq 1 ]]; then
        "$glidein_cvmfsexec_dir/$dist_file" "$config_repository" -- echo "setting up mount utilities..." &> /dev/null
    fi
    # at this point in the execution flow, it would have been determined that cvmfs is not locally available
    # this implies no repositories should be mounted. However, only config repo will be mounted if in mode 1 or mode 3 by this point
    if [[ $(df -h|grep /cvmfs|wc -l) -eq 1 ]]; then
        loginfo "CVMFS config repo already mounted!"
    else
        # mounting the configuration repo (pre-requisite) in case something went wrong previously
        loginfo "Mounting CVMFS config repo now..."
        [[ $cvmfsexec_mode -eq 1 ]] && "$glidein_cvmfsexec_dir"/.cvmfsexec/mountrepo "$config_repository"
        [[ $cvmfsexec_mode -eq 3 ]] && $CVMFSMOUNT "$config_repository"
    fi
    # see if the config repository got mounted
    config_repo_mntd=$(df -h | grep /cvmfs | wc -l)
    if [[ config_repo_mntd -eq 0 ]]; then
        logwarn "One or more CVMFS repositories might not be mounted on the worker node"
        return 1
    fi

    # using an array to unpack the names of additional CVMFS repositories
    # from the colon-delimited string
    repos=($(echo $additional_repos | tr ":" "\n"))

    loginfo "Mounting additional CVMFS repositories..."
    # mount every repository that was previously unpacked
    [[ "$cvmfsexec_mode" -ne 1 && "$cvmfsexec_mode" -ne 3 ]] && { logerror "Invalid cvmfsexec mode: mode $cvmfsexec_mode; aborting!"; return 1; }
    for repo in "${repos[@]}"
    do
        case $cvmfsexec_mode in
            1)
                "$glidein_cvmfsexec_dir"/.cvmfsexec/mountrepo "$repo"
                ;;
            3)
                $CVMFSMOUNT "$repo"
                ;;
        esac
    done

    # see if all the repositories got mounted
    num_repos_mntd=$(df -h | grep /cvmfs | wc -l)
    total_num_repos=$(( ${#repos[@]} + 1 ))
    GWMS_IS_CVMFS=0
    if [[ "$num_repos_mntd" -eq "$total_num_repos" ]]; then
        loginfo "All CVMFS repositories mounted successfully on the worker node"
        # export this info to the glidein environment after CVMFS is provisioned on demand
        gconfig_add GWMS_IS_CVMFS $(print_exit_status $GWMS_IS_CVMFS)
        get_mount_point
        return 0
    else
        logwarn "One or more CVMFS repositories might not be mounted on the worker node"
        GWMS_IS_CVMFS=1
        return 1
    fi
}


get_mount_point() {
    # DESCRIPTION: This function is used to obtain the mount point information regarding where CVMFS is mounted on deman (when mounted). By default, CVMFS when mounted is at '/cvmfs'. Otherwise, CVMFS will be mounted at <glidein_work_dir>/.cvmfsexec/dist/cvmfs
    #
    # INPUT(S): None
    # RETURN(S): None

    mount_point=$(findmnt -t fuse -S /dev/fuse | tail -n 1 | cut -d ' ' -f 1 )
    if [[ -n "$mount_point" && "$mount_point" != TARGET* ]]; then
        mount_point=$(dirname "$mount_point")
        if [[ -n "$mount_point" && "$mount_point" != /cvmfs ]]; then
            CVMFS_MOUNT_DIR="$mount_point"
            export CVMFS_MOUNT_DIR=$mount_point
            gconfig_add CVMFS_MOUNT_DIR "$mount_point"
        fi
    fi
}


has_unpriv_userns() {
    # DESCRIPTION: This function checks the status of unprivileged user
    # namespaces being supported and enabled on the worker node.
    #
    # INPUT(S): None
    # RETURN(S):
    #	-> true (0) if unpriv userns can be used (supported and enabled),
    #	false otherwise
    #	-> status of unpriv userns (unavailable, disabled, enabled,
    #	error) to stdout

    # make sure that perform_system_check has run
    [[ -z "${GWMS_SYSTEM_CHECK}" ]] && perform_system_check

    # determine whether unprivileged user namespaces are supported and enabled...
    if [[ "${GWMS_IS_UNPRIV_USERNS_ENABLED}" -eq 0 ]]; then
        # if unprivileged user namespaces is enabled in the system
        if [[ "${GWMS_IS_UNPRIV_USERNS_SUPPORTED}" -eq 0 ]]; then
            # check if unprivileged user namespaces is supported by the system
            loginfo "Unprivileged user namespaces supported and enabled"
            echo enabled
	        return 0
        fi
        # otherwise, if unprivileged user namespaces is not supported by the system
        logerror "Inconsistent system configuration: unprivileged usernamespaces is enabled but not supported"
        echo error
    else
        # if unprivileged user namespaces is found to be disabled
        if [[ "${GWMS_IS_UNPRIV_USERNS_SUPPORTED}" -eq 0 ]]; then
            # unprivileged user namespaces is supported
            logwarn "Unprivileged user namespaces disabled: can be enabled by the root user via sysctl"
            echo disabled
        else
            # otherwise, if unprivileged user namespaces is also not supported by the system
            logwarn "Unprivileged user namespaces disabled and unsupported: can be supported/enabled only after a system upgrade"
            echo unavailable
        fi
    fi
    return 1
}


has_fuse() {
    # DESCRIPTION: This function checks the status of FUSE configuration being available on the worker node.
    #
    # INPUT(S): None
    # RETURN(S):
    #	-> true (0) if FUSE is available, false otherwise
    #	-> status of FUSE configuration (no, yes, error) to stdout

    # make sure that perform_system_check has run
    [[ -n "${GWMS_SYSTEM_CHECK}" ]] && perform_system_check

    # determine which cvmfsexec utilities can be used by checking availability of fuse, fusermount and user being in fuse group...
    if [[ "${GWMS_IS_FUSE_INSTALLED}" -ne 0 ]]; then
        # fuse is not installed
	    if [[ "${GWMS_IS_FUSERMOUNT}" -eq 0 ]]; then
	        # fusermount is somehow available and user is/is not in fuse group (scenarios 3,4)
	        logwarn "Inconsistent system configuration: fusermount is only available with fuse and/or when user belongs to the fuse group"
            echo error
        else
            # fusermount is not available and user is/is not in fuse group (scenarios case 1,2)
            loginfo "FUSE requirements not satisfied: fusermount is not available"
            echo no
        fi
	    return 1
    fi

    # fuse rpm is installed
    local ret_state
    if [[ $unpriv_userns_status = "unavailable" ]]; then
        # unprivileged user namespaces unsupported, i.e. kernels 2.x (scenarios 5b,6b)
        if [[ "${GWMS_IS_USR_IN_FUSE_GRP}" -eq 0 ]]; then
            # user is in fuse group -> fusermount is available (scenario 6b)
            if [[ "${GWMS_IS_FUSERMOUNT}" -ne 0 ]]; then
                logwarn "Inconsistent system configuration: fusermount is available with fuse installed and when user is in fuse group"
                ret_state=error
            else
                loginfo "FUSE requirements met by the worker node"
                ret_state=yes
            fi
        else
            # user is not in fuse group -> fusermount is unavailable (scenario 5b)
            if [[ "${GWMS_IS_FUSERMOUNT}" -eq 0 ]]; then
                logwarn "Inconsistent system configuration: fusermount is available only when user is in fuse group and fuse is installed"
                ret_state=error
            else
                loginfo "FUSE requirements not satisfied: user is not in fuse group"
                ret_state=no
            fi
        fi        
    else
        # unprivileged user namespaces is either enabled or disabled
        if [[ "${GWMS_IS_FUSERMOUNT}" -eq 0 ]]; then
            # fuse is installed with fusermount available (scenarios 7,8)
            loginfo "FUSE requirements met by the worker node"
            ret_state=yes
        else
            # fuse is installed but fusermount not available (scenarios 5a,6a)
            logwarn "Inconsistent system configuration: fusermount is not available when fuse is installed "
            ret_state=error
        fi
    fi
    echo $ret_state
    [[ "$ret_state" == "yes" ]]
    return
}


determine_cvmfsexec_mode_usage() {
    # DESCRIPTION: This function is used to determine the cvmfsexec mode that will be applicable based on the worker node specifications, including the status of unprivileged user namespaces and FUSE configuration.
    #
    # INPUT(S): None
    # RETURN(S):
    #	-> true (0) if it is determined that one of the three cvmfsexec modes can be used, false otherwise
    #	-> an integer indicating the mode of cvmfsexec that will be possible (0, 1, 2, 3) to stdout

    # make sure that perform_system_check has run
    [[ -z "${GWMS_SYSTEM_CHECK}" ]] && perform_system_check
    
    # check what specific configuration of unprivileged user namespaces exists in the system (worker node)
    unpriv_userns_status=$(has_unpriv_userns)

    # check FUSE configuration on the worker node
    fuse_config_status=$(has_fuse)

    if [[ "${unpriv_userns_status}" == "error" && "${fuse_config_status}" == "error" ]]; then
        logwarn "User namespaces and fuse mounts not available in unprivileged mode"
        echo 0
        return 1
    fi
    # either 1. if unprivileged user namespaces are enabled (and therefore supported)
    if  [[ "${unpriv_userns_status}" == "enabled" ]]; then
        # satisfies the minimum requirement for mode 3
        if [[ $GWMS_OS_KRNL_VER -ge 5 || $GWMS_OS_KRNL_VER -ge 4 && $GWMS_OS_KRNL_MAJOR_REV -ge 18 || $GWMS_OS_KRNL_VER -ge 3 && $GWMS_OS_KRNL_MAJOR_REV -ge 10 && $GWMS_OS_KRNL_MINOR_REV -ge 0 && $GWMS_OS_KRNL_PATCH_NUM -ge 1127 ]]; then
            # if newer kernels >= 4.18 (RHEL8) or >= 3.10.0-1127 (RHEL 7.8), cvmfsexec can be used in mode 3
            echo 3
            return 0
        fi
        # if RHEL <= 7.7, cvmfsexec can be used in mode 2
        echo 2
        return 0
    elif [[ "${unpriv_userns_status}" =~ ^(disabled|unavailable)$ ]]; then
        # when unpriv. userns are disabled/not available, take FUSE status into consideration
        if [[ "${fuse_config_status}" != "yes" ]]; then
            # cvmfsexec cannot be used in either of the three modes
            loginfo "cvmfsexec cannot be used in either of the three modes!"
            echo 0
            return 1
        fi
    fi
    # or 2. solely based on fuse status on the worker node, determine whether any of the cvmfsexec modes can be used
    if [[ "${fuse_config_status}" == "yes" ]]; then
        # cvmfsexec can be used in mode 1
        echo 1
        return 0
    fi
    if [[ $fuse_config_status == no ]]; then
        # failure;
        logerror "CVMFS cannot be mounted on the worker node using mountrepo utility"
    elif [[ $fuse_config_status == error ]]; then
        # inconsistent system configurations detected in the worker node
        logerror "Detected inconsistent configurations on the worker node. mountrepo utility cannot be used!!"
    fi
    echo 0
    return 1
}


setup_cvmfsexec_use() {
    # DESCRIPTION: This function performs the necessary setup prior to using cvmfsexec, if possible. If cvmfsexec can be used in either of the three modes, the specific mode information is written to the glidein configuration file.
    #
    # INPUT(S): None
    # RETURN(S): an integer depicting the cvmfsexec mode that is applicable for the worker node.

    local gwms_cvmfsexec_mode
    # first we perform checks on the worker node that will be used to assess whether cvmfsexec can be used and if yes, which mode of cvmfsexec can be used
    [[ -z "${GWMS_SYSTEM_CHECK}" ]] && perform_system_check

    # second, log the results of the checks that were performed in the previous step
    log_all_system_info

    # finally, using the results obtained from the checks, determine which mode of cvmfsexec can be used
    gwms_cvmfsexec_mode=$(determine_cvmfsexec_mode_usage)
    if [[ $gwms_cvmfsexec_mode -ne 0 ]]; then
        gconfig_add GWMS_CVMFSEXEC_MODE $gwms_cvmfsexec_mode
    fi
    echo $gwms_cvmfsexec_mode
}


prepare_for_cvmfs_mount () {
    # DESCRIPTION: This function is used to prepare the necessary items and keep them ready/accessible right before mounting CVMFS on demand. 
    #
    # INPUT(S): None
    # RETURN(S): None

    # if not previously performed, perform checks on the worker node that will be used to assess whether CVMFS can be mounted or not
    [[ -z "${GWMS_SYSTEM_CHECK}" ]] && perform_system_check

    # get the CVMFS source information from <attr> in the glidein configuration
    cvmfs_source=$(gconfig_get CVMFS_SRC "$glidein_config")

    # get the directory where cvmfsexec is unpacked
    glidein_cvmfsexec_dir=$(gconfig_get CVMFSEXEC_DIR "$glidein_config")

    # gather the worker node information to construct the name of the cvmfsexec distribution file based on the worker node specs
    # perform_system_check sets a few variables that can be helpful here
    os_like=$GWMS_OS_DISTRO
    os_ver=$GWMS_OS_VERSION_MAJOR
    arch=$GWMS_OS_KRNL_ARCH
    # construct the name of the cvmfsexec distribution file based on the worker node specs
    dist_file=cvmfsexec-${cvmfs_source}-${os_like}${os_ver}-${arch}
    # the appropriate distribution file does not have to manually untarred as the glidein setup takes care of this automatically

    if [[ ! -d "$glidein_cvmfsexec_dir" && ! -f "${glidein_cvmfsexec_dir}/${dist_file}" ]]; then
        # neither the cvmfsexec directory nor the cvmfsexec distribution is found -- this happens when a directory named 'cvmfsexec' does not exist on the glidein because an appropriate distribution tarball is not found in the list of all the available tarballs and was not unpacked [trying to unpack osg-rhel8 on osg-rhel7 worker node]
        # if use_cvmfsexec is set to 1, then warn that cvmfs will not be mounted and flag an error
        logerror "Error occured during preparing for cvmfs setup: None of the available cvmfsexec distributions is compatible with the worker node specifications."
        "$error_gen" -error "$(basename $0)" "WN_Resource" "Error occured during cvmfs setup... no matching cvmfsexec distribution available."
        exit 1
    elif [[ -d "$glidein_cvmfsexec_dir" && ! -f "${glidein_cvmfsexec_dir}/${dist_file}" ]]; then
        # something might have gone wrong during the unpacking of the tarball into the glidein_cvmfsexec_dir
        logerror "Something went wrong during the unpacking of the cvmfsexec distribution tarball!"
        "$error_gen" -error "$(basename $0)" "WN_Resource" "Error: Something went wrong during the unpacking of the cvmfsexec distribution tarball"
        exit 1
    fi

    loginfo "CVMFS Source = $cvmfs_source"
    # initializing CVMFS repositories to a variable for easy modification in the future
    case $cvmfs_source in
        osg)
            GLIDEIN_CVMFS_CONFIG_REPO=config-osg.opensciencegrid.org
            GLIDEIN_CVMFS_REPOS=singularity.opensciencegrid.org:cms.cern.ch:oasis.opensciencegrid.org
            ;;
        egi)
            GLIDEIN_CVMFS_CONFIG_REPO=config-egi.egi.eu
            GLIDEIN_CVMFS_REPOS=config-osg.opensciencegrid.org:singularity.opensciencegrid.org:cms.cern.ch:oasis.opensciencegrid.org
            ;;
        default)
            GLIDEIN_CVMFS_CONFIG_REPO=cvmfs-config.cern.ch
            GLIDEIN_CVMFS_REPOS=config-osg.opensciencegrid.org:singularity.opensciencegrid.org:cms.cern.ch:oasis.opensciencegrid.org
            ;;
        *)
            "$error_gen" -error "$(basename "$0")" "WN_Resource" "Invalid factory attribute value specified for CVMFS source."
            exit 1
    esac
    # (optional) set an environment variable that suggests additional repos to be mounted after config repos are mounted
    loginfo "CVMFS Config Repo = $GLIDEIN_CVMFS_CONFIG_REPO"
    loginfo "CVMFS Repos = $GLIDEIN_CVMFS_REPOS"
}


perform_cvmfs_mount () {
    # DESCRIPTION: This function serves as a wrapper for performing mounting of CVMFS on demand depending on a few factors. 
    #
    # INPUT(S): an integer denoting the selected cvmfsexec mode
    # RETURN(S): to stdout one of the following values:
    #	-> true (0) if CVMFS was mounted successfully without any errors
    #	-> false (1) if CVMFS was not mounted successfully due to errors
    #   -> false (2) if CVMFS was not mounted because the OS distribution found on the worker node is not rhel-based (only RHEL distros are supported as of now).

    local mode=$1
    # if not previously performed, assess the worker node based on its existing system configurations and perform next steps to mount CVMFS
    [[ -z "${GWMS_SYSTEM_CHECK}" ]] && perform_system_check

    # if strict requirement of CVMFS mounting is not set to 'never' (i.e. 'required' or 'preferred')
    # by this point, it would have been established that CVMFS is not locally available, so install CVMFS via one of the three modes of cvmfsexec
    loginfo "Mounting CVMFS on demand using mode $mode of cvmfsexec"
    # check the operating system distribution
    if [[ "${GWMS_OS_DISTRO}" != "rhel" ]]; then
        # if operating system distribution is non-RHEL (any non-rhel OS)
        print_os_info
        logwarn "This is a non-RHEL OS and is not covered in the implementation yet!"
        return 2
        # ----- Further Implementation: TBD (To Be Done) ----- #
    fi
   
    prepare_for_cvmfs_mount
    if [[ $mode -eq 3 || $mode -eq 2 ]]; then
        return       # only prepare but do not actually mount (later in glidein reinvocation, mounting will be performed)
    fi
    loginfo "Mounting CVMFS repositories..."
    if ! mount_cvmfs_repos $mode $GLIDEIN_CVMFS_CONFIG_REPO $GLIDEIN_CVMFS_REPOS ; then
        return 1
    fi
    return 0
}
