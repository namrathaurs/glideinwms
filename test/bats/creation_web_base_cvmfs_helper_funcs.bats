#!/usr/bin/env bats

# SPDX-FileCopyrightText: 2009 Fermi Research Alliance, LLC
# SPDX-License-Identifier: Apache-2.0

[[ -z "$GWMS_SOURCEDIR" ]] && GWMS_SOURCEDIR=../..

setup() {
    source compat.bash
    source "$GWMS_SOURCEDIR"/creation/web_base/cvmfs_helper_funcs.sh fixtures/glidein_config 2>&3 || true
}

@test "Test cvmfsexec mode usage when unpriv. user namespaces is enabled" {
    # mocking the below two functions to ensure that
    # the test case uses what is defined above
    #stub has_unpriv_userns
    #mock_set_stdout "enabled"
    #stub has_fuse
    #mock_set_stdout "yes"
    has_unpriv_userns() { echo "enabled"; }
    has_fuse() { echo "yes"; }

    run determine_cvmfsexec_mode_usage
    [[ $output == "3" ]] || false
    [ $status -eq 0 ]

    has_fuse() { echo "no"; }
    run determine_cvmfsexec_mode_usage
    [[ $output == "3" ]] || false
    [ $status -eq 0 ]

    has_fuse() { echo "error"; }
    run determine_cvmfsexec_mode_usage
    [[ $output == "3" ]] || false
    [ $status -eq 0 ]
}

@test "Test cvmfsexec mode usage when unpriv. user namespaces is disabled" {
    # mocking the below two functions to ensure that
    # the test case uses what is defined above
    has_unpriv_userns() { echo "disabled"; }
    has_fuse() { echo "yes"; }
    run determine_cvmfsexec_mode_usage
    [[ $output == "1" ]] || false
    [ $status -eq 0 ]

    has_fuse() { echo "no"; }
    run determine_cvmfsexec_mode_usage
    [[ ${lines[1]} == "0" ]] || false
    [ $status -eq 1 ]

    has_fuse() { echo "error"; }
    run determine_cvmfsexec_mode_usage
    [[ ${lines[1]} == "0" ]] || false
    [ $status -eq 1 ]
}

@test "Test cvmfsexec mode usage when unpriv. user namespaces is unavailable" {
    # mocking the below two functions to ensure that
    # the test case uses what is defined above
    has_unpriv_userns() { echo "unavailable"; }
    has_fuse() { echo "yes"; }
    run determine_cvmfsexec_mode_usage
    [[ $output == "1" ]] || false
    [ $status -eq 0 ]

    has_fuse() { echo "no"; }
    run determine_cvmfsexec_mode_usage
    [[ ${lines[1]} == "0" ]] || false
    [ $status -eq 1 ]

    has_fuse() { echo "error"; }
    run determine_cvmfsexec_mode_usage
    [[ ${lines[1]} == "0" ]] || false
    [ $status -eq 1 ]
}

@test "Test cvmfsexec mode usage when unpriv. user namespaces is error" {
    # mocking the below two functions to ensure that
    # the test case uses what is defined above
    has_unpriv_userns() { echo "error"; }
    has_fuse() { echo "yes"; }
    run determine_cvmfsexec_mode_usage
    [[ $output == "1" ]] || false
    [ $status -eq 0 ]

    has_fuse() { echo "no"; }
    run determine_cvmfsexec_mode_usage
    [[ ${lines[1]} == "0" ]] || false
    [ $status -eq 1 ]

    has_fuse() { echo "error"; }
    run determine_cvmfsexec_mode_usage
    [[ ${lines[1]} == "0" ]] || false
    [ $status -eq 1 ]
}

@test "Test unprivileged user namespaces status 1" {
    # when unpriv. user namespaces is not supported but enabled (weird state)
    perform_system_check() { GWMS_IS_UNPRIV_USERNS_ENABLED=0; GWMS_IS_UNPRIV_USERNS_SUPPORTED=1; }
    run has_unpriv_userns
    [[ ${lines[1]} == "error" ]] || false
    [ $status -eq 1 ]
}

@test "Test unprivileged user namespaces status 2" {
    # when unpriv. user namespaces is supported and enabled
    perform_system_check() { GWMS_IS_UNPRIV_USERNS_ENABLED=0; GWMS_IS_UNPRIV_USERNS_SUPPORTED=0; }
    run has_unpriv_userns
    [[ ${lines[1]} == "enabled" ]] || false
    [ $status -eq 0 ]
}

@test "Test unprivileged user namespaces status 3" {
    # when unpriv. user namespaces is not supported and disabled
    perform_system_check() { GWMS_IS_UNPRIV_USERNS_ENABLED=1; GWMS_IS_UNPRIV_USERNS_SUPPORTED=1; }
    run has_unpriv_userns
    [[ ${lines[1]} == "unavailable" ]] || false
    [ $status -eq 1 ]
}

@test "Test unprivileged user namespaces status 4" {
    # when unpriv. user namespaces is supported but disabled
    perform_system_check() { GWMS_IS_UNPRIV_USERNS_ENABLED=1; GWMS_IS_UNPRIV_USERNS_SUPPORTED=0; }
    run has_unpriv_userns
    [[ ${lines[1]} == "disabled" ]] || false
    [ $status -eq 1 ]
}

@test "Test fuse configuration status 1" {
    perform_system_check() { GWMS_IS_FUSE_INSTALLED=1; GWMS_IS_FUSERMOUNT=0; }
    run has_fuse
    echo "GWMS_IS_FUSE_INSTALLED: $GWMS_IS_FUSE_INSTALLED" >&3
    echo "GWMS_IS_FUSERMOUNT: $GWMS_IS_FUSERMOUNT" >&3
    echo "MY OUTPUT IS: $output" >&3
    [[ ${lines[1]} == "error" ]] || false
    [ $status -eq 0 ]
}

@test "Test fuse configuration status 2" {
    perform_system_check() { GWMS_IS_FUSE_INSTALLED=1; GWMS_IS_FUSERMOUNT=1; }
    run has_fuse
    echo "MY OUTPUT IS: $output" >&3
    [[ ${lines[1]} == "no" ]] || false
    [ $status -eq 0 ]
}

@test "Test fuse configuration status 3" {
    perform_system_check() { GWMS_IS_FUSE_INSTALLED=0; GWMS_IS_FUSERMOUNT=0; }
    run has_fuse
    [[ ${lines[1]} == "yes" ]] || false
    [ $status -eq 0 ]
}

@test "Test fuse configuration status 4" {
    perform_system_check() { GWMS_IS_FUSE_INSTALLED=0; GWMS_IS_FUSERMOUNT=1; }
    run has_fuse
    echo "MY OUTPUT IS: $output" >&3
    [[ ${lines[1]} == "error" ]] || false
    [ $status -eq 0 ]
}
