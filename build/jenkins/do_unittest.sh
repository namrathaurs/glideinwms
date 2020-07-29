# Shell source file to be sourced to run Python unit tests and coverage
# To be used only inside runtest.sh (runtest.sh and util.sh functions defined, VARIABLES available)
# All function names start with do_...

do_help_msg() {
  cat << EOF
${COMMAND} command:
${filename} [options] ${COMMAND} [other command options] TEST_FILES
  Runs the unit tests on TEST_FILES files in glidinwms/unittests/
${filename} [options] ${COMMAND} -a [other command options]
  Run the unit tests on all the files in glidinwms/unittests/ named test_*
Runs unit tests and exit the results to standard output. Failed tests will cause also a line starting with ERROR.
Command options:
  -h        print this message
  -a        run on all unit tests (see above)
  -c        generate a coverage report while running unit tests
EOF
}

LIST_FILES=
RUN_COVERAGE=

do_parse_options () {
    while getopts ":hac" option
    do
      case "${option}"
      in
      h) help_msg; do_help_msg; exit 0;;
      a) LIST_FILES=yes;;
      c) RUN_COVERAGE=yes;;
      : ) logerror "illegal option: -$OPTARG requires an argument"; help_msg 1>&2; exit 1;;
      *) logerror "illegal option: -$OPTARG"; help_msg 1>&2; exit 1;;
      ##\?) logerror "illegal option: -$OPTARG"; help_msg 1>&2; exit 1;;
      esac
    done

    shift $((OPTIND-1))

    CMD_OPTIONS="$@"
}

do_use_python() { true; }

do_count_failures() {
    # Counts the failures using bats output (print format)
    # Uses implicit $file (test file) $tmp_out (stdout form test execution)
    # 1 - test execution exit code
    # BATS exit codes
    # 0 - no failed tests
    # 1 - failed tests
    # >1 - execution error (e.g. 126 wrong permission)
    fail=0
    local tmp_fail=
    if [[ $1 -eq 1 ]]; then
        lline="$(echo "$tmp_out" | grep "FAILED (")"
        if [[ "$lline" == "FAILED ("* ]]; then
            tmp_fail="${lline##*=}"
            fail=${tmp_fail%)}
            #(echo "$lline" | cut -f3 -d' ')
        fi
    fi
    fail_files=$((fail_files + 1))
    fail_all=$((fail_all + fail))
    logerror "Test $file failed ($1): $fail failed tests"
    return $1
}

do_process_branch() {
    # 1 - branch
    # 2 - output file (output directory/output.branch)
    # 3... - files to process (optional)
    #

    if ! cd unittests ; then
        logexit "cannot find the test directory './unittests', exiting"
    fi

    local branch="$1"
    local branch_no_slash=$(echo "${1}" | sed -e 's/\//_/g')
    local outfile="$2"
    local out_coverage="${outfile}.coverage_report"
    local out_cov_html="${outfile}.coverage_html.d"
    local outdir="$(dirname "$2")"
    local outfilename="$(basename "$2")"
    # test_outdir defined and created below
    shift 2

    # Example file lists (space separated list)
    #files="test_frontend.py"
    #files="test_frontend_element.py"
    #files="test_frontend.py test_frontend_element.py"
    local files_list
    if [[ -n "$LIST_FILES" ]]; then
        #files_list="$(find . -readable -name  'test_*.py' -print)"
        files_list="$(get_files_pattern "test_*.py")"
    else
        files_list="$*"
    fi

    print_files_list "Python will use the following unit test files:" "${files_list}" && return

    local test_date=$(date "+%Y-%m-%d %H:%M:%S")
    SOURCES="$(get_source_directories)"
    local test_outdir="${outfile}.d"
    mkdir -p "${test_outdir}"

    [[ -n "$RUN_COVERAGE" ]] && coverage erase

    local -i fail=0
    local -i fail_files=0
    local -i fail_all=0
    local tmp_out=
    local tmp_out_file=
    local -i tmp_exit_code
    local -i exit_code
    for file in ${files_list} ; do
        loginfo "TESTING ==========> $file"
#        if [[ -n "$RUN_COVERAGE" ]]; then
#            tmp_out="$(coverage run   --source="${SOURCES}" --omit="test_*.py"  -a "$file")" || log_verbose_nonzero_rc "$file" $?
#        else
#            tmp_out="$(./"$file")" || log_verbose_nonzero_rc "$file" $?
#        fi
        if [[ -n "$RUN_COVERAGE" ]]; then
            tmp_out="$(coverage run   --source="${SOURCES}" --omit="test_*.py"  -a "$file" 2>&1)" || do_count_failures $?
        else
            tmp_out="$(./"$file" 2>&1)" || do_count_failures $?
        fi
        tmp_exit_code=$?
        [[ ${tmp_exit_code} -gt ${exit_code} ]] && exit_code=${tmp_exit_code}

        tmp_out_file="${test_outdir}/$(basename "${file%.*}").txt"
        [[ -e "$tmp_out_file" ]] && echo "WARNING: duplicate file name, overwriting tests results: $tmp_out_file"
        echo "$tmp_out" > "${tmp_out_file}"

    done

    if [[ -n "$RUN_COVERAGE" ]]; then
        TITLE="GlideinWMS Coverage Report for branch $branch on $test_date"
        coverage report > "${out_coverage}"
        coverage html --title "$TITLE" || logwarn "coverage html report failed"
        if [[ -d htmlcov ]]; then
            mv htmlcov "${out_cov_html}"
        else
            # To help troubleshooting the coverage failure
            logwarn "no html coverage report generated for $branch_no_slash on $(hostname)"
            command -v coverage || logwarn "coverage not installed"
            coverage --version || logwarn "coverage not installed"
        fi
    fi

    # TODO: find numbers and fix
    echo "# Python unittest output" > "${outfile}"
    echo "PYUNITTEST_FILES_CHECKED=\"${files_list}\"" >> "${outfile}"
    echo "PYUNITTEST_FILES_CHECKED_COUNT=`echo ${files_list} | wc -w | tr -d " "`" >> "${outfile}"
    echo "PYUNITTEST_ERROR_FILES_COUNT=${fail_files}" >> "${outfile}"
    echo "PYUNITTEST_ERROR_COUNT=${fail_all}" >> "${outfile}"
    echo "----------------"
    cat "${outfile}"
    echo "----------------"

    return ${exit_code}

}