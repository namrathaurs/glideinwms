# SPDX-FileCopyrightText: 2009 Fermi Research Alliance, LLC
# SPDX-License-Identifier: Apache-2.0

"""This module implements classes to query the condor daemons and manipulate the results
Please notice that it also converts \" into "
"""

import copy
import os
import socket
import xml.parsers.expat

from itertools import groupby

from . import condorExe, condorSecurity

USE_HTCONDOR_PYTHON_BINDINGS = False
try:
    # NOTE:
    # import htcondor tries to look for CONDOR_CONFIG in the usual search path
    # If it cannot be found, it will print annoying error message which
    # neither goes to stdout nor stderr. It was not clear how to mask this
    # message so we may have to live with it till then
    # In case of non default locations of CONDOR_CONFIG, frontend will always
    # set the CONDOR_CONFIG appropriately before every command. Since import
    # happens before frontend can do anything, htcondor module is initialized
    # without the knowledge of CONDOR_CONFIG. A reload is needed.
    # Furthermore, _CONDOR_ variables are ignored by htcondor and need to be added
    # manually to htcondor.param.
    # This mandates that we do a htcondor_full_reload() every time to use the bindings.
    import classad  # pylint: disable=import-error
    import htcondor  # pylint: disable=import-error

    USE_HTCONDOR_PYTHON_BINDINGS = True
except ImportError:
    # TODO Maybe we should print a message here? Even though I don't know if
    # logSupport has been initialized. But I'd try to put it log.debug
    pass


def htcondor_full_reload():
    """Reloads the HTCondor configuration from the environment and updates HTCondor parameters.

    If the HTCondor Python bindings are enabled, this function reloads the configuration by reading the
    `CONDOR_CONFIG` environment variable and manually adds `_CONDOR_` prefixed environment variables to
    the HTCondor parameters.
    """
    HTCONDOR_ENV_PREFIX = "_CONDOR_"
    HTCONDOR_ENV_PREFIX_LEN = len(HTCONDOR_ENV_PREFIX)  # Length of _CONDOR_ = 8
    if not USE_HTCONDOR_PYTHON_BINDINGS:
        return
    # Reload configuration reading CONDOR_CONFIG from the environment
    htcondor.reload_config()
    # _CONDOR_ variables need to be added manually to _Params
    for i in os.environ:
        if i.startswith(HTCONDOR_ENV_PREFIX):
            htcondor.param[i[HTCONDOR_ENV_PREFIX_LEN:]] = os.environ[i]


#
# Configuration
#


def set_path(new_condor_bin_path):
    """Sets the path to the HTCondor binaries.

    Args:
        new_condor_bin_path (str): The new path to the Condor binaries.
    """
    global condor_bin_path
    condor_bin_path = new_condor_bin_path


#
# Exceptions
#


class QueryError(RuntimeError):
    """Thrown when there are exceptions using htcondor python bindings or commands."""

    def __init__(self, err_str):
        RuntimeError.__init__(self, err_str)


class PBError(RuntimeError):
    """Thrown when there are exceptions using htcondor python bindings."""

    def __init__(self, err_str):
        RuntimeError.__init__(self, err_str)


#
# Caching classes
#


class NoneScheddCache:
    """Dummy caching class, when you don't want caching.
    Used as base class below, too.
    """

    def getScheddId(self, schedd_name, pool_name):
        """Given the schedd name and pool name, return a tuple (ScheddCmdOption, env dict).

        The environment dictionary could contain variables like LOCAL_DIR.

        Args:
            schedd_name (str or None): The name of the schedd. If None, an empty string is returned as option.
            pool_name (str or None): The pool name.

        Returns:
            tuple: Tuple with schedd command string option, env (empty dictionary).
        """
        return self.iGetCmdScheddStr(schedd_name), {}

    def iGetCmdScheddStr(self, schedd_name):
        """Constructs a command string option for the specified schedd name.

        Args:
            schedd_name (str or None): The name of the schedd. If None, an empty string is returned.

        Returns:
            str: The command string for the schedd. If `schedd_name` is None, returns an empty string.
                 Otherwise, returns the command string with the schedd name.
        """
        if schedd_name is None:
            schedd_str = ""
        else:
            schedd_str = "-name %s " % schedd_name

        return schedd_str


class LocalScheddCache(NoneScheddCache):
    """Schedd caching class.

    The schedd can be found either through -name attr or through the local disk lookup.
    Remembers which one to use.
    """

    def __init__(self):
        """Initializes the schedd cache with default settings.

        Attributes:
            enabled (bool): Indicates if the instance is enabled. Default is True.
            cache (dict): A dictionary to store schedd and pool name mappings to their respective CMS argument strings and environments.
            my_ips (list): A list of IP addresses associated with the current host, including localhost if defined.
        """
        self.enabled = True
        # dict of (schedd_name,pool_name)=>(cms arg schedd string,env)
        self.cache = {}
        self.my_ips = socket.gethostbyname_ex(socket.gethostname())[2]
        try:
            self.my_ips += socket.gethostbyname_ex("localhost")[2]
        except socket.gaierror:
            pass  # localhost not defined, ignore

    def enable(self):
        """Enables the cache.

        Sets the `enabled` attribute to True.
        """
        self.enabled = True

    def disable(self):
        """Disables the cache.

        Sets the `enabled` attribute to False.
        """
        self.enabled = False

    def getScheddId(self, schedd_name, pool_name):
        """Given the schedd name and pool name, get a tuple containing (ScheddId, dict).

        Args:
            schedd_name (str or None): The name of the schedd. If None, an empty string is returned as option.
            pool_name (str or None): The pool name.

        Returns:
            tuple: Tuple with the schedd (command option) string, and env.
        """
        if schedd_name is None:  # special case, do not cache
            return "", {}

        if self.enabled:
            k = (schedd_name, pool_name)
            if k not in self.cache:  # not in cache, discover it
                env = self.iGetEnv(schedd_name, pool_name)
                if env is None:
                    self.cache[k] = (self.iGetCmdScheddStr(schedd_name), {})
                else:
                    # TODO: MM - Possible bug? Analyze cache use. Should this be "" or the schedd name?
                    self.cache[k] = ("", env)
            return self.cache[k]
        else:
            # Not enabled, just return the str
            return self.iGetCmdScheddStr(schedd_name), {}

    #
    # PRIVATE
    #
    def iGetEnv(self, schedd_name, pool_name):
        """Retrieves the HTCondor environment settings for the spool directory for the specified schedd.

        This method checks the disk cache for existing data. If not found, it fetches the data from the HTCondor status.
        It also checks if the schedd is local and if it is advertising its SPOOL or LOCAL directory.

        Args:
            schedd_name (str): The name of the schedd.
            pool_name (str): The name of the pool.

        Returns:
            dict or None: A dictionary with the environment settings for the schedd if applicable,
                          or None if the directory does not exist or if the schedd is not local.

        Raises:
            RuntimeError: If the schedd is not found or if it is not advertising `ScheddIpAddr`.
            Exception: Other exceptions may be raised during the fetching or processing of data.
        """
        global disk_cache
        data = disk_cache.get(schedd_name + ".igetenv")  # pylint: disable=assignment-from-none
        if data is None:
            cs = CondorStatus("schedd", pool_name)
            data = cs.fetch(
                constraint='Name=?="%s"' % schedd_name,
                format_list=[("ScheddIpAddr", "s"), ("SPOOL_DIR_STRING", "s"), ("LOCAL_DIR_STRING", "s")],
            )
            disk_cache.save(schedd_name + ".igetenv", data)
        if schedd_name not in data:
            raise RuntimeError("Schedd '%s' not found" % schedd_name)

        el = data[schedd_name]
        if "SPOOL_DIR_STRING" not in el and "LOCAL_DIR_STRING" not in el:
            # Not advertising, cannot use disk optimization
            return None
        if "ScheddIpAddr" not in el:
            # This should never happen
            raise RuntimeError(f"Schedd '{schedd_name}' is not advertising ScheddIpAddr")

        schedd_ip = el["ScheddIpAddr"][1:].split(":")[0]
        if schedd_ip in self.my_ips:  # Seems local, go for the directory
            l_dir = el.get("SPOOL_DIR_STRING", el.get("LOCAL_DIR_STRING"))
            if os.path.isdir(l_dir):  # Making sure the directory exists
                if "SPOOL_DIR_STRING" in el:
                    return {"_CONDOR_SPOOL": "%s" % l_dir}
                else:  # LOCAL_DIR_STRING, assuming spool is LOCAL_DIR_STRING/spool
                    if os.path.isdir("%s/spool" % l_dir):
                        return {"_CONDOR_SPOOL": "%s/spool" % l_dir}
            else:
                # Directory does not exist, not relevant, revert to standard behavior
                return None
        else:
            # Not local
            return None


# The class does not belong here, it should be in the disk_cache module.
# However, condorMonitor is not importing anything from glideinwms.lib, it is a standalon module
# We might revisit this in the future
class NoneDiskCache:
    """Dummy class used if a regular DiskCache is not specified."""

    def get(self, objid):
        return None

    def save(self, objid, obj):
        return None


# default global object
local_schedd_cache = LocalScheddCache()
disk_cache = NoneDiskCache()


def condorq_attrs(q_constraint, attribute_list):
    """Retrieves a list of a single item from  all the factory queues.

    Args:
        q_constraint (str): Query constraint.
        attribute_list (list): List of attributes to return.

    Returns:
        list: List of query proxy.
    """
    attr_str = ""
    for attr in attribute_list:
        attr_str += " -attr %s" % attr

    xml_data = condorExe.exe_cmd("condor_q", f"-g -l {attr_str} -xml -constraint '{q_constraint}'")

    classads_xml = []
    tmp_list = []
    for line in xml_data:
        # look for the xml header
        if line[:5] == "<?xml":
            if len(tmp_list) > 0:
                classads_xml.append(tmp_list)
            tmp_list = []
        tmp_list.append(line)

    q_proxy_list = []
    for ad_xml in classads_xml:
        cred_list = xml2list(ad_xml)
        q_proxy_list.extend(cred_list)

    return q_proxy_list


#
# Condor monitoring classes
#


class AbstractQuery:
    """Abstract (pure virtual) class to have a minimum set of methods defined."""

    def fetch(self, constraint=None, format_list=None):
        """Fetch the classad attributes specified in the format list matching the constraint.

        Abstract method to be implemented in child classes.

        Args:
            constraint (str, optional): Query constraint. Defaults to no constraint (None).
            format_list (list, optional): List of attributes to return and formats. Defaults to None.

        Returns:
            dict: Dict containing classad attributes and values
        """
        raise NotImplementedError("Fetch not implemented")

    def load(self, constraint=None, format_list=None):
        """Fetch the data and store it in self.stored_data.

        Abstract method to be implemented in child classes.

        Args:
            constraint(str, optional): Query constraint. Defaults to no constraint (None).
            format_list(list, optional): List of attributes to return and formats. Defaults to None.
        """
        raise NotImplementedError("Load not implemented")

    def fetchStored(self, constraint_func=None):
        """Fetch the stored query data.

        Abstract method to be implemented in child classes.

        Args:
            constraint_func (function, optional): A boolean function, with only one argument (data el).
                Defaults to None, return all the data.

        Returns:
            dict: Same as fetch(), but limited to `constraint_func(el)==True`.
        """
        raise NotImplementedError("fetchStored not implemented")


class StoredQuery(AbstractQuery):
    """Abstract (virtual) class that implements fetchStored."""

    stored_data = {}

    def fetchStored(self, constraint_func=None):
        """Fetch the stored query data.

        Abstract method to be implemented in child classes.

        Args:
            constraint_func (function, optional): A boolean function, with only one argument (data el).
                Defaults to None, return all the data.

        Returns:
            dict: Same as fetch(), but limited to `constraint_func(el)==True`.
        """
        return applyConstraint(self.stored_data, constraint_func)


class CondorQEdit:
    """Fully implemented class that executes condorq_edit commands. Only provides a method to do bulk
    updates of jobs using transaction-based API and the condor python bindings.
    Cannot be used without HTCondor Python bindings.
    """

    def __init__(self, pool_name=None, schedd_name=None):
        """Constructor.

        Args:
            pool_name (str, optional): Pool name. Defaults to the local Collector pool.
            schedd_name (str, optional): Schedd name. Defaults to the local schedd.

        Raises:
            QueryError: In case HTCondor Python bindings are not available.
        """
        self.pool_name = pool_name
        self.schedd_name = schedd_name
        if not USE_HTCONDOR_PYTHON_BINDINGS:
            raise QueryError("QEdit class only implemented with python bindings")

    def executeAll(self, joblist=None, attributes=None, values=None):
        """Given equal sized lists of job ids, attributes and values,
        executes in one large transaction a single qedit for each job.

        Args:
            joblist (list, optional): List of jobs. Defaults to an empty list (None).
            attributes (list, optional): List of attributes. Defaults to an empty list (None).
            values (list, optional): List of values. Defaults to an empty list (None).

        Raises:
            QueryError: If there are problems with the parameters or the operation.
        """
        global disk_cache
        joblist = joblist or []
        attributes = attributes or []
        values = values or []
        if not (len(joblist) == len(attributes) == len(values)):
            raise QueryError("Arguments to QEdit.executeAll should have the same length")
        try:
            htcondor_full_reload()
            if self.pool_name:
                collector = htcondor.Collector(str(self.pool_name))
            else:
                collector = htcondor.Collector()

            if self.schedd_name:
                schedd_ad = disk_cache.get(self.schedd_name + ".locate")  # pylint: disable=assignment-from-none
                if schedd_ad is None:
                    schedd_ad = collector.locate(htcondor.DaemonTypes.Schedd, self.schedd_name)
                    disk_cache.save(self.schedd_name + ".locate", schedd_ad)

                schedd = htcondor.Schedd(schedd_ad)
            else:
                schedd = htcondor.Schedd()
            with schedd.transaction() as _:
                for jobid, attr, val in zip(joblist, attributes, values):
                    schedd.edit([jobid], attr, classad.quote(val))
        except Exception as ex:
            s = "default"
            if self.schedd_name is not None:
                s = self.schedd_name
            p = "default"
            if self.pool_name is not None:
                p = self.pool_name
            try:
                j1 = jobid
                j2 = attr
                j3 = val
            except Exception:
                j1 = j2 = j3 = "unknown"
            err_str = (
                "Error querying schedd %s in pool %s using python bindings (qedit of job/attr/val %s/%s/%s): %s"
                % (s, p, j1, j2, j3, ex)
            )
            raise QueryError(err_str) from ex


#
# format_list is a list of
#  (attr_name, attr_type)
# where attr_type is one of
#  "s" - string
#  "i" - integer
#  "r" - real (float)
#  "b" - bool
#
#
# security_obj, if defined, should be a child of condorSecurity.ProtoRequest
class CondorQuery(StoredQuery):
    """Fully implemented class that executes condor commands."""

    def __init__(self, exe_name, resource_str, group_attribute, pool_name=None, security_obj=None, env={}):
        """Initializes a new instance of the class.

        Args:
            exe_name (str): The name of the executable.
            resource_str (str): The resource string.
            group_attribute (str): The group attribute.
            pool_name (str, optional): The name of the pool. Defaults to None.
            security_obj (object, optional): The security object. Defaults to None.
            env (dict, optional): The environment variables. Defaults to an empty dictionary.
        """
        self.exe_name = exe_name
        self.env = env
        self.resource_str = resource_str
        self.group_attribute = group_attribute
        self.pool_name = pool_name
        if pool_name is None:
            self.pool_str = ""
        else:
            self.pool_str = "-pool %s" % pool_name

        if security_obj is not None:
            if security_obj.has_saved_state():
                raise RuntimeError("Cannot use a security object which has saved state.")
            self.security_obj = copy.deepcopy(security_obj)
        else:
            self.security_obj = condorSecurity.ProtoRequest()

    def require_integrity(self, requested_integrity):
        """Set client integrity settings to use for condor commands.

        Args:
            requested_integrity (str): HTCondor integrity level.
        """
        if requested_integrity is None:
            condor_val = None
        elif requested_integrity:
            condor_val = "REQUIRED"
        else:
            # Not required, set OPTIONAL if the other side requires it
            condor_val = "OPTIONAL"
        self.security_obj.set("CLIENT", "INTEGRITY", condor_val)

    def get_requested_integrity(self):
        """Get the current integrity settings.

        Returns:
            bool or None: None->None; REQUIRED->True; OPTIONAL->False.
        """
        condor_val = self.security_obj.get("CLIENT", "INTEGRITY")
        if condor_val is None:
            return None
        return condor_val == "REQUIRED"

    def require_encryption(self, requested_encryption):
        """Set client encryption settings to use for condor commands.

        Args:
            requested_encryption (str): HTCondor encryption level.
        """
        if requested_encryption is None:
            condor_val = None
        elif requested_encryption:
            condor_val = "REQUIRED"
        else:
            # Not required, set OPTIONAL if the other side requires it
            condor_val = "OPTIONAL"
        self.security_obj.set("CLIENT", "ENCRYPTION", condor_val)

    def get_requested_encryption(self):
        """Get the current encryption settings.

        Returns:
            bool or None: None->None; REQUIRED->True; OPTIONAL->False.
        """
        condor_val = self.security_obj.get("CLIENT", "ENCRYPTION")
        if condor_val is None:
            return None
        return condor_val == "REQUIRED"

    def fetch(self, constraint=None, format_list=None):
        """Return the results obtained using HTCondor commands or python bindings.

        Args:
            constraint (str, optional): Query constraint. Defaults to None.
            format_list (list, optional): Classad attr & type. Defaults to None.
                                          Example: `[(attr1, 'i'), ('attr2', 's')]`.

        Returns:
            dict: Dict containing the query results.

        Raises:
            QueryError: If an error occurs during the query execution.
        """
        try:
            if USE_HTCONDOR_PYTHON_BINDINGS:
                return self.fetch_using_bindings(constraint=constraint, format_list=format_list)
            else:
                return self.fetch_using_exe(constraint=constraint, format_list=format_list)
        except Exception as ex:
            err_str = (
                "Error executing htcondor query to pool %s with constraint %s and format_list %s: %s. Env is %s"
                % (self.pool_name, constraint, format_list, ex, os.environ)
            )
            raise QueryError(err_str) from ex

    def fetch_using_exe(self, constraint=None, format_list=None):
        """Return the results obtained from executing the HTCondor query command.

        Args:
            constraint (str, optional): Constraints to be applied to the query. Defaults to None.
            format_list (list, optional): Classad attr and type. Defaults to None.
                                          Example: `[(attr1, 'i'), ('attr2', 's')]`

        Returns:
            dict: Dictionary containing the results.

        """
        if constraint is None:
            constraint_str = ""
        else:
            constraint_str = "-constraint '%s'" % constraint

        full_xml = format_list is None
        if format_list is not None:
            format_arr = []
            for format_el in format_list:
                attr_name, attr_type = format_el
                attr_format = {"s": "%s", "i": "%i", "r": "%f", "b": "%i"}[attr_type]
                format_arr.append(f'-format "{attr_format}" "{attr_name}"')
            format_str = " ".join(format_arr)

        # set environment for security settings
        self.security_obj.save_state()
        try:
            self.security_obj.enforce_requests()

            if full_xml:
                xml_data = condorExe.exe_cmd(
                    self.exe_name, f"{self.resource_str} -xml {self.pool_str} {constraint_str}", env=self.env
                )
            else:
                # format_str is defined because full_xml False means (format_list is not None)
                xml_data = condorExe.exe_cmd(
                    self.exe_name,
                    f"{self.resource_str} {format_str} -xml {self.pool_str} {constraint_str}",  # pylint: disable=E0606
                    env=self.env,
                )
        finally:
            # restore old security context
            self.security_obj.restore_state()

        list_data = xml2list(xml_data)
        del xml_data
        dict_data = list2dict(list_data, self.group_attribute)
        return dict_data

    def fetch_using_bindings(self, constraint=None, format_list=None):
        """Fetch the results using htcondor-python bindings.

        Args:
            constraint (str, optional): Constraints to be applied to the query. Defaults to None.
            format_list (list, optional): Classad attr & type. Defaults to None.
                                          Example: `[(attr1, 'i'), ('attr2', 's')]`

        Returns:
            dict: Dictionary containing the results.

        Raises:
            NotImplementedError: The operation is not implemented using bindings.

        """
        raise NotImplementedError("fetch_using_bindings() not implemented")

    def load(self, constraint=None, format_list=None):
        """Fetch the results and cache it in self.stored_data.

        Args:
            constraint (str, optional): Constraints to be applied to the query. Defaults to None.
            format_list (list, optional): Classad attr & type. Defaults to None.
                                          Example: `[(attr1, 'i'), ('attr2', 's')]`
        """
        self.stored_data = self.fetch(constraint, format_list)

    def __repr__(self):
        """Returns a string representation of the HTCondor query.

        Returns a string containing detailed information about the HTCondor query's attributes.

        Returns:
            str: A string representation of the HTCondor query.
        """
        output = "%s:\n" % self.__class__.__name__
        output += "exe_name = %s\n" % str(self.exe_name)
        output += "env = %s\n" % str(self.env)
        output += "resource_str = %s\n" % str(self.resource_str)
        output += "group_attribute = %s\n" % str(self.group_attribute)
        output += "pool_name = %s\n" % str(self.pool_name)
        output += "pool_str = %s\n" % str(self.pool_str)
        output += "security_obj = %s\n" % str(self.security_obj)
        output += "used_python_bindings = %s\n" % USE_HTCONDOR_PYTHON_BINDINGS
        output += "stored_data = %s" % str(self.stored_data)
        return output


class CondorQ(CondorQuery):
    """Class to implement condor_q. Uses htcondor-python bindings if possible."""

    def __init__(self, schedd_name=None, pool_name=None, security_obj=None, schedd_lookup_cache=local_schedd_cache):
        """Initializes a new instance of the class.

        Args:
            schedd_name (str, optional): The name of the schedd. Defaults to None.
            pool_name (str, optional): The name of the pool. Defaults to None.
            security_obj (object, optional): The security object. Defaults to None.
            schedd_lookup_cache (object, optional): The cache object used for schedd lookup.
                                                    Defaults to local_schedd_cache if not provided.
        """
        self.schedd_name = schedd_name

        if schedd_lookup_cache is None:
            schedd_lookup_cache = NoneScheddCache()

        schedd_str, env = schedd_lookup_cache.getScheddId(schedd_name, pool_name)
        CondorQuery.__init__(self, "condor_q", schedd_str, ["ClusterId", "ProcId"], pool_name, security_obj, env)

    def fetch(self, constraint=None, format_list=None):
        """Fetches data from the Condor query.

        Args:
            constraint (str, optional): A constraint to filter the query results. Defaults to None.
            format_list (list of tuple, optional): A list of attributes to include in the query results.
                                                   Defaults to None.

        Returns:
            list: A list of query results.
        """
        if format_list is not None:
            # If format_list, make sure ClusterId and ProcId are present
            format_list = complete_format_list(format_list, [("ClusterId", "i"), ("ProcId", "i")])
        return CondorQuery.fetch(self, constraint=constraint, format_list=format_list)

    def fetch_using_bindings(self, constraint=None, format_list=None):
        """Fetch the condor_q results using htcondor-python bindings.

        Args:
            constraint (str, optional): Constraints to be applied to the query. Defaults to None.
            format_list (list, optional): Classad attr & type. Defaults to None.
                                          Example: `[(attr1, 'i'), ('attr2', 's')]`

        Returns:
            dict: Dictionary containing the results.
        """
        global disk_cache
        results_dict = {}  # defined here in case of exception
        constraint = bindings_friendly_constraint(constraint)
        attrs = bindings_friendly_attrs(format_list)

        self.security_obj.save_state()
        try:
            self.security_obj.enforce_requests()
            htcondor_full_reload()
            if self.pool_name:
                collector = htcondor.Collector(str(self.pool_name))
            else:
                collector = htcondor.Collector()

            if self.schedd_name is None:
                schedd = htcondor.Schedd()
            else:
                schedd_ad = disk_cache.get(self.schedd_name + ".locate")  # pylint: disable=assignment-from-none
                if schedd_ad is None:
                    schedd_ad = collector.locate(htcondor.DaemonTypes.Schedd, self.schedd_name)
                    disk_cache.save(self.schedd_name + ".locate", schedd_ad)
                schedd = htcondor.Schedd(schedd_ad)
            results = schedd.query(constraint, attrs)
            results_dict = list2dict(results, self.group_attribute)
        except Exception as ex:
            s = "default"
            if self.schedd_name is not None:
                s = self.schedd_name
            p = "default"
            if self.pool_name is not None:
                p = self.pool_name
            err_str = f"Error querying schedd {s} in pool {p} using python bindings: {ex}"
            raise PBError(err_str) from ex
        finally:
            self.security_obj.restore_state()

        return results_dict


class CondorStatus(CondorQuery):
    """Class to implement the condor_status command. Uses htcondor-python bindings if possible."""

    def __init__(self, subsystem_name=None, pool_name=None, security_obj=None):
        """Constructor.

        Args:
            subsystem_name (str, optional): Subsystem name. Defaults to "" (None).
            pool_name (str, optional): Pool name. Defaults to the local pool (None).
            security_obj (object, optional): The security object. Defaults to None.
        """
        if subsystem_name is None:
            subsystem_str = ""
        else:
            subsystem_str = "-%s" % subsystem_name
        CondorQuery.__init__(self, "condor_status", subsystem_str, "Name", pool_name, security_obj, {})

    def fetch(self, constraint=None, format_list=None):
        """Fetch the condor_status results using htcondor-python bindings if available, the command otherwise.

        Args:
            constraint (str, optional): Constraints to be applied to the query. Defaults to None.
            format_list (list, optional): Classad attr & type. Defaults to None.
                                          Example: `[(attr1, 'i'), ('attr2', 's')]`

        Returns:
            dict: Dictionary containing the results.
        """
        if format_list is not None:
            # If format_list, make sure Name is present
            format_list = complete_format_list(format_list, [("Name", "s")])
        return CondorQuery.fetch(self, constraint=constraint, format_list=format_list)

    def fetch_using_bindings(self, constraint=None, format_list=None):
        """Fetch the results using htcondor-python bindings.

        Args:
            constraint (str, optional): Constraints to be applied to the query. Defaults to None.
            format_list (list, optional): Classad attr & type. Defaults to None.
                                          Example: `[(attr1, 'i'), ('attr2', 's')]`

        Returns:
            dict: Dictionary containing the results.
        """
        results_dict = {}  # defined here in case of exception
        constraint = bindings_friendly_constraint(constraint)
        attrs = bindings_friendly_attrs(format_list)

        adtype = resource_str_to_py_adtype(self.resource_str)
        self.security_obj.save_state()
        try:
            self.security_obj.enforce_requests()
            htcondor_full_reload()
            if self.pool_name:
                collector = htcondor.Collector(str(self.pool_name))
            else:
                collector = htcondor.Collector()

            results = collector.query(adtype, constraint, attrs)
            results_dict = list2dict(results, self.group_attribute)
        except Exception as ex:
            p = "default"
            if self.pool_name is not None:
                p = self.pool_name
            err_str = f"Error querying pool {p} using python bindings: {ex}"
            raise PBError(err_str) from ex
        finally:
            self.security_obj.restore_state()

        return results_dict


#
# Subquery classes
#


class BaseSubQuery(StoredQuery):
    """Abstract (virtual) class that implements fetch for `StoredQuery()` for a sub-query.
    Sub-queries apply a subquery function to the data fetched by the query instead of the formatting in the
    attribute list of regular queries.
    """

    def __init__(self, query, subquery_func):
        """Initializes a new instance of the class.

        Args:
            query (AbstractQuery): The query object.
            subquery_func (function): The function used for subquery processing.
        """
        self.query = query
        self.subquery_func = subquery_func

    def fetch(self, constraint=None):
        """Fetches data based on the provided query and applies the subquery function.

        Args:
            constraint (str, optional): A constraint to filter the query results. Defaults to None.

        Returns:
            object: The result of applying the subquery function to the fetched data.
        """
        indata = self.query.fetch(constraint)
        return self.subquery_func(self, indata)

    #
    # NOTE: You need to call load on the SubQuery object to use fetchStored
    #       and had query.load issued before
    #
    def load(self, constraint=None):
        """Loads data using a stored query and applies the subquery function to it.

        NOTE: You need to call `load` on the SubQuery object to use `fetchStored` and have `query.load` issued before.

        Args:
            constraint (str, optional): A constraint to filter the query results. Defaults to None.
        """
        indata = self.query.fetchStored(constraint)
        self.stored_data = self.subquery_func(indata)


class SubQuery(BaseSubQuery):
    """Fully usable subquery class, typically used on CondorQ() or CondorStatus()."""

    def __init__(self, query, constraint_func=None):
        """Initializes a new instance of the class.

        Args:
            query (AbstractQuery): The query object.
            constraint_func (function, optional): A function to apply constraints. Defaults to None.
        """
        BaseSubQuery.__init__(self, query, lambda d: applyConstraint(d, constraint_func))

    def __repr__(self):
        """Returns a string representation of the object.

        Returns:
            str: A string representation of the object.
        """
        output = "%s:\n" % self.__class__.__name__
        # output += "client_name = %s\n" % str(self.client_name)
        # output += "entry_name = %s\n" % str(self.entry_name)
        # output += "factory_name = %s\n" % str(self.factory_name)
        # output += "glidein_name = %s\n" % str(self.glidein_name)
        # output += "schedd_name = %s\n" % str(self.schedd_name)
        output += "stored_data = %s" % str(self.stored_data)
        return output


class Group(BaseSubQuery):
    """Sub Query class with grouping functionality.
    Each element has a value that is the summary of the values in a group.
    """

    def __init__(self, query, group_key_func, group_data_func):
        """Constructor.

        Args:
            query (AbstractQuery): Query.
            group_key_func (function): Key extraction function.
                                       One argument: classad dictionary.
                                       Returns: value of the group key.
            group_data_func (function): Group extraction function.
                                        One argument: list of classad dictionaries.
                                        Returns: a summary classad dictionary.
        """
        BaseSubQuery.__init__(self, query, lambda d: doGroup(d, group_key_func, group_data_func))


class NestedGroup(BaseSubQuery):
    """Sub Query class with grouping functionality to create nested results.
    Each element is a dictionary with elements reduced from the original elements in the group.
    """

    def __init__(self, query, group_key_func, group_element_func=None):
        """Constructor.

        Args:
            query (AbstractQuery): Query.
            group_key_func (function): Key extraction function.
                                       One argument: classad dictionary.
                                       Returns: value of the group key.
            group_element_func (function, optional): Group extraction function.
                                                     One argument: list of tuples (key, classad dictionaries).
                                                     Returns: a dictionary of classad dictionary.
                                                     Defaults to `dict` (when None).
        """
        BaseSubQuery.__init__(self, query, lambda d: doNestedGroup(d, group_key_func, group_element_func))


class Summarize:
    """Class summarizing other classes.

    Attributes:
        query (object): The query to summarize.
        hash_func (function): The hashing function.
                              It has one argument: classad dictionary.
                              Returns the hash value:
                              - if None, the element will not be counted.
                              - if a list, all elements will be used.
    """

    def __init__(self, query, hash_func=lambda x: 1):
        """Initializes a new instance of the summarizing class.

        Args:
            query (object): The query object.
            hash_func (function, optional): The hashing function. Defaults to a function that always returns 1.
        """
        self.query = query
        self.hash_func = hash_func

    def count(self, constraint=None, hash_func=None, flat_hash=False):
        """Counts occurrences of items based on the query results.

        Args:
            constraint (str, optional): A constraint to filter the query results (passed to `query.fetch()`).
                                        Defaults to None.
            hash_func (function, optional): A custom hashing function to use instead of the main one.
                                            Defaults to None (i.e. using the main one).
            flat_hash (bool, optional): Whether to return a flat dictionary or nested dictionaries. Defaults to False.

        Returns:
            dict: A dictionary of hash values with counts.
                  Elements are counts (or more dictionaries if hash returns lists)
        """
        data = self.query.fetch(constraint)
        if flat_hash:
            return fetch2count_flat(data, self._get_hash(hash_func))
        return fetch2count(data, self._get_hash(hash_func))

    def countStored(self, constraint_func=None, hash_func=None, flat_hash=False):
        """Counts occurrences of items based on pre-stored query results.

        Args:
            constraint_func (function, optional): A constraint function to filter the stored query results. Defaults to None.
            hash_func (function, optional): A custom hashing function to use instead of the main one. Defaults to None.
            flat_hash (bool, optional): Whether to return a flat dictionary or nested dictionaries. Defaults to False.

        Returns:
            dict: A dictionary of hash values with counts.
        """
        data = self.query.fetchStored(constraint_func)
        if flat_hash:
            return fetch2count_flat(data, self._get_hash(hash_func))
        return fetch2count(data, self._get_hash(hash_func))

    def list(self, constraint=None, hash_func=None):
        """Lists items based on the query results.

        Args:
            constraint (str, optional): A constraint to filter the query results. Defaults to None.
            hash_func (function, optional): A custom hashing function to use instead of the main one. Defaults to None.

        Returns:
            dict: A dictionary of hash values with lists of keys.
                  Elements are lists of keys (or more dictionaries if hash returns lists)
        """
        data = self.query.fetch(constraint)
        return fetch2list(data, self._get_hash(hash_func))

    def listStored(self, constraint_func=None, hash_func=None):
        """Lists items based on pre-stored query results.

        Args:
            constraint_func (function, optional): A constraint function to filter the stored query results. Defaults to None.
            hash_func (function, optional): A custom hashing function to use instead of the main one. Defaults to None.

        Returns:
            dict: A dictionary of hash values with lists of keys.
                  Elements are lists of keys (or more dictionaries if hash returns lists)
        """
        data = self.query.fetchStored(constraint_func)
        return fetch2list(data, self._get_hash(hash_func))

    # Internal
    def _get_hash(self, hash_func):
        """Get the hash function to use. Returns the main (class) hash function if the parameter is None.

        Args:
            hash_func (function): The custom hash function, if provided.

        Returns:
            function: The hash function to use.
        """
        if hash_func is None:
            return self.hash_func
        else:
            return hash_func


############################################################
#
# P R I V A T E, do not use
#
############################################################


def complete_format_list(in_format_list, req_format_els):
    """Checks if required format elements are present in the input format list, and if not, adds them.

    Args:
        in_format_list (list): The input format list.
        req_format_els (list): The list of required format elements.

    Returns:
        list: The new format list with required elements added if missing.
    """
    out_format_list = in_format_list[0:]
    for req_format_el in req_format_els:
        found = False
        for format_el in in_format_list:
            if format_el[0] == req_format_el[0]:
                found = True
                break
        if not found:
            out_format_list.append(req_format_el)
    return out_format_list


#
# Convert Condor XML to list
#
# HTCondor XML example:
#
# <?xml version="1.0"?>
# <!DOCTYPE classads SYSTEM "classads.dtd">
# <classads>
# <c>
#    <a n="MyType"><s>Job</s></a>
#    <a n="TargetType"><s>Machine</s></a>
#    <a n="AutoClusterId"><i>0</i></a>
#    <a n="ExitBySignal"><b v="f"/></a>
#    <a n="TransferOutputRemaps"><un/></a>
#    <a n="WhenToTransferOutput"><s>ON_EXIT</s></a>
# </c>
# <c>
#    <a n="MyType"><s>Job</s></a>
#    <a n="TargetType"><s>Machine</s></a>
#    <a n="AutoClusterId"><i>0</i></a>
#    <a n="OnExitRemove"><b v="t"/></a>
#    <a n="x509userproxysubject"><s>/DC=gov/DC=fnal/O=Fermilab/OU=People/CN=Igor Sfiligoi/UID=sfiligoi</s></a>
# </c>
# </classads>
#


# 3 xml2list XML handler functions
def xml2list_start_element(name, attrs):
    """XML handler function called when starting an XML element.

    Args:
        name (str): The name of the XML element.
        attrs (dict): The attributes of the XML element.

    Raises:
        TypeError: If the XML element type is not supported.
    """
    global xml2list_data, xml2list_inclassad, xml2list_inattr, xml2list_intype
    if name == "c":
        xml2list_inclassad = {}
    elif name == "a":
        xml2list_inattr = {"name": attrs["n"], "val": ""}
        xml2list_intype = "s"
    elif name == "i":
        xml2list_intype = "i"
    elif name == "r":
        xml2list_intype = "r"
    elif name == "b":
        xml2list_intype = "b"
        if "v" in attrs:
            xml2list_inattr["val"] = attrs["v"] in ("T", "t", "1")  # pylint: disable=unsupported-assignment-operation
        else:
            # extended syntax... value in text area
            xml2list_inattr["val"] = None  # pylint: disable=unsupported-assignment-operation
    elif name == "un":
        xml2list_intype = "un"
        xml2list_inattr["val"] = None  # pylint: disable=unsupported-assignment-operation
    elif name in ("s", "e"):
        pass  # nothing to do
    elif name == "classads":
        pass  # top element, nothing to do
    else:
        raise TypeError("Unsupported type: %s" % name)


def xml2list_end_element(name):
    """XML handler function called when encountering the end of an XML element.

    Args:
        name (str): The name of the XML element.

    Global Variables:
        xml2list_data (list): A list containing parsed classad dictionaries.
        xml2list_inclassad (dict): The current classad dictionary being parsed.
        xml2list_inattr (dict): The current attribute dictionary within the classad being parsed.
        xml2list_intype (str): The data type of the current attribute value ('i' for integer, 'r' for float,
                               'b' for boolean, 'un' for unknown type).

    Raises:
        TypeError: If an unexpected XML element type is encountered.

    Notes:
        - If the XML element is 'c' (classad), appends the current classad dictionary to xml2list_data.
        - If the XML element is 'a' (attribute), adds the attribute to the current classad dictionary.
        - Resets xml2list_intype to 's' (string) if the XML element is one of 'i', 'b', 'un', or 'r'.
        - Handles cases where the XML element name is 's' (string), 'e' (end), or 'classads' by passing silently.
        - Raises a TypeError if an unexpected XML element type is encountered.
    """
    global xml2list_data, xml2list_inclassad, xml2list_inattr, xml2list_intype
    # Would like to reset, but the following would be resetting global variables and failing ./test_frontend.py
    # xml2list_data, xml2list_inclassad, xml2list_inattr, xml2list_intype = {}

    if name == "c":
        xml2list_data.append(xml2list_inclassad)
        xml2list_inclassad = None
    elif name == "a":
        xml2list_inclassad[xml2list_inattr["name"]] = xml2list_inattr["val"]  # pylint: disable=unsubscriptable-object
        xml2list_inattr = None
    elif name in ("i", "b", "un", "r"):
        xml2list_intype = "s"
    elif name in ("s", "e"):
        pass  # Nothing to do for string and expression markers
    elif name == "classads":
        pass  # Top element, nothing to do
    else:
        raise TypeError("Unexpected type: %s" % name)


def xml2list_char_data(data):
    """XML handler function called when receiving character data within an XML element.

    Args:
        data (str): The character data received.

    Global Variables:
        xml2list_data (list): A list containing parsed classad dictionaries.
        xml2list_inclassad (dict): The current classad dictionary being parsed.
        xml2list_inattr (dict): The current attribute dictionary within the classad being parsed.
        xml2list_intype (str): The data type of the current attribute value ('i' for integer, 'r' for float,
                               'b' for boolean, 'un' for unknown type).

    Notes:
        - This function updates the xml2list_inattr["val"] with parsed data based on xml2list_intype.
        - If xml2list_intype is 'b' and xml2list_inattr["val"] is None, it interprets the data as boolean.
        - Handles unescaped double quotes in the data by replacing '\\"' with '"'.
    """
    global xml2list_data, xml2list_inclassad, xml2list_inattr, xml2list_intype

    if xml2list_inattr is None:
        # Only process when inside an attribute
        return

    if xml2list_intype == "i":
        xml2list_inattr["val"] = int(data)
    elif xml2list_intype == "r":
        xml2list_inattr["val"] = float(data)
    elif xml2list_intype == "b":
        if xml2list_inattr["val"] is not None:
            # Value was already in attribute, nothing to do
            pass
        else:
            # Interpret the first character of data as boolean value
            xml2list_inattr["val"] = data[0] in ("T", "t", "1")
    elif xml2list_intype == "un":
        # Value was already in attribute, nothing to do
        pass
    else:
        # Append unescaped data to the current attribute value
        unescaped_data = data.replace('\\"', '"')
        xml2list_inattr["val"] += unescaped_data


def xml2list(xml_data):
    """Parse XML data representing Condor classads and convert it into a list of dictionaries.

    This function parses the XML data using the Expat parser and extracts classads and their attributes.

    Args:
        xml_data (list of str): The XML data representing Condor classads.

    Returns:
        list of dict: A list containing dictionaries, where each dictionary represents a classad.

    Global Variables:
        xml2list_data (list): A list containing parsed classad dictionaries.
        xml2list_inclassad (dict): The current classad dictionary being parsed.
        xml2list_inattr (dict): The current attribute dictionary within the classad being parsed.
        xml2list_intype (str): The data type of the current attribute value ('i' for integer, 'r' for float,
                               'b' for boolean, 'un' for unknown type).

    Raises:
        RuntimeError: If there's an error parsing the XML data.
    """
    global xml2list_data, xml2list_inclassad, xml2list_inattr, xml2list_intype

    # Initialize global variables
    xml2list_data = []
    xml2list_inclassad = None
    xml2list_inattr = None
    xml2list_intype = None

    # Create an Expat parser
    p = xml.parsers.expat.ParserCreate()

    # Set XML handler functions
    p.StartElementHandler = xml2list_start_element
    p.EndElementHandler = xml2list_end_element
    p.CharacterDataHandler = xml2list_char_data

    # Find the position of the XML header
    found_xml = -1
    for line in range(len(xml_data)):
        # Look for the xml header
        if xml_data[line][:5] == "<?xml":
            found_xml = line
            break

    # Parse XML data
    if found_xml >= 0:
        try:
            p.Parse(" ".join(xml_data[found_xml:]), 1)
        except TypeError as e:
            raise RuntimeError("Failed to parse XML data, TypeError: %s" % e) from e
        except Exception as e:
            raise RuntimeError("Failed to parse XML data, generic error") from e
    # else no xml, so return an empty list

    return xml2list_data


def list2dict(list_data, attr_name):
    """Convert a list to a dictionary where the keys are tuples with the values of the attributes listed in attr_name.

    Original description: Convert a list to a dictionary and group the results based on
    attributes specified by `attr_name`.

    This function has a couple of quirks, but is OK because the ways it is used (MM)
    The way it is used, attr_name is the job cluster, process, which are both present in all jobs from condor_q and
    unique, or the Name that is always present and unique in condor_status, so the quirks should not cause problems.
    1. Type checking (of attr_name) probably should use isistance()
    2. dict_name is a tuple including elements of attr_name translated to value in list_el
       if them or the lowercase is a key in list_el
       BUT from the value ( dict_data[dict_name] ) only exact match is excluded, not the lowercase version
    3. keys (dict_name) may have different cardinality if one or some of the elements is not matching list_el keys
    4. if 2 or more list_el have the same dict_name (same values in attr_list attributes), the newest ones overwrite
       the older ones without any warning
       AND the original description mentions ... "and group the results" ... there is no grouping
    5. 'Undefined' attributes are not added to the dict_el (dict elements may have different keys)
    6. using `'%s'%a_value != 'Undefined'` and  `str(list_el[a]) != 'Undefined'` for the same. Use twice the better one

    Args:
        list_data: list of dictionaries to convert.
        attr_name: string (1 attribute) or list or tuple (one or more attributes) with the attributes to use as key.

    Returns:
        dict: dictionary of dictionaries.

    """

    if type(attr_name) in (type([]), type((1, 2))):
        attr_list = attr_name
    else:
        attr_list = [attr_name]

    dict_data = {}
    for list_el in list_data:
        if type(attr_name) in (type([]), type((1, 2))):
            dict_name = []
            for an in attr_name:
                if an in list_el:
                    dict_name.append(list_el[an])
                else:
                    # Try lower cases
                    for k in list_el:
                        if an.lower() == k.lower():
                            dict_name.append(list_el[k])
                            break
            dict_name = tuple(dict_name)
        else:
            dict_name = list_el[attr_name]
        # dict_el will have all the elements but those in attr_list
        dict_el = {}
        for a in list_el:
            if a not in attr_list:
                try:
                    if USE_HTCONDOR_PYTHON_BINDINGS:
                        if list_el[a].__class__.__name__ == "ExprTree":
                            # Try to evaluate the condor expr and use its value
                            # If cannot be evaluated, keep the expr as is
                            a_value = list_el[a].eval()
                            if "%s" % a_value != "Undefined":
                                # Cannot use classad.Value.Undefined for
                                # for comparison as it gets cast to int
                                dict_el[a] = a_value
                        elif str(list_el[a]) != "Undefined":
                            # No need for Undefined check to see if
                            # attribute exists in the fetched classad
                            dict_el[a] = list_el[a]
                    else:
                        dict_el[a] = list_el[a]
                except Exception:
                    # Do not fail
                    pass

        dict_data[dict_name] = dict_el
    return dict_data


def applyConstraint(data, constraint_func):
    """Return a subset of data that satisfies constraint_function.
    If constraint_func is None, return back entire data.

    Args:
        data (dict): Data to filter
        constraint_func (function or None): Constraint function. Returns True to include a value in the results.
                                            If None, return all the data.

    Returns:
        dict: Dictionary with constrained data.
    """

    if constraint_func is None:
        return data
    else:
        outdata = {}
        for key, val in data.items():
            if constraint_func(val):
                outdata[key] = val
    return outdata


def doGroup(indata, group_key_func, group_data_func):
    """Group the indata based on the keys that satisfy group_key_func (applied to the value).
    Return a dict of groups summarized by group_data_func.
    Each group returned by group_data_func must be a dictionary,
    possibly similar to the original value of the indata elements.

    Args:
        indata:
        group_key_func:
        group_data_func:

    Returns:
        dict: Dictionary of groups summarized by group_data_func.
    """

    gdata = {}
    for k, inel in indata.items():
        gkey = group_key_func(inel)
        if gkey in gdata:
            gdata[gkey].append(inel)
        else:
            gdata[gkey] = [inel]

    outdata = {}
    for k in gdata:
        # value is a summary of the values
        outdata[k] = group_data_func(gdata[k])

    return outdata


def doNestedGroup(indata, group_key_func, group_element_func=None):
    """Group the indata based on the keys that satisfy group_key_func (applied to the value).
    Return a dict of dictionaries created by group_element_func.
    Each value of the dictionaries returned by group_element_func
    must be a dictionary, possibly similar to the original value of the indata elements.

    If group_element_func is None (not provided), then the dictionaries in the groups are a copy of the
    original dictionaries in indata.

    Args:
        indata: data to group.
        group_key_func: group_by function.
        group_element_func: how to handle the data in each group (by default is a copy of the original one).

    Returns:
        dict: Dictionary of dictionaries with grouped indata.

    """

    gdata = {}
    for k, inel in indata.items():
        gkey = group_key_func(inel)
        if gkey in gdata:
            gdata[gkey].append((k, inel))
        else:
            gdata[gkey] = [(k, inel)]

    outdata = {}
    if group_element_func:
        for k in gdata:
            # dictionary produced using  original dictionary elements in the group
            outdata[k] = group_element_func(gdata[k])
    else:
        for k in gdata:
            # just grouping the original elements without changing them
            outdata[k] = dict(gdata[k])

    return outdata


def fetch2count(data, hash_func):
    """Nested count of the hash values returned from all the elements in data.

    Args:
        data: data from a fetch().
        hash_func: Hashing function
            One argument: classad dictionary
            Returns: hash value
                if None, will not be counted
                if a list, all elements will be used

    Returns:
        dict: Dictionary of hash values.
              Elements are counts (or more dictionaries if hash returns lists).

    """
    count = {}
    for k in list(data.keys()):
        el = data[k]

        hid = hash_func(el)
        if hid is None:
            # hash tells us it does not want to count this
            continue

        # cel will point to the real counter
        cel = count

        # check if it is a list
        if isinstance(hid, list):
            # have to create structure inside count
            for h in hid[:-1]:
                if h not in cel:
                    cel[h] = {}
                cel = cel[h]
            hid = hid[-1]

        if hid in cel:
            count_el = cel[hid] + 1
        else:
            count_el = 1
        cel[hid] = count_el

    return count


def fetch2count_flat(data, hash_func):
    """Count the hash values returned from all the elements in data.

    Args:
        data: data from a fetch()
        hash_func (function or None): Hashing function
                   One argument: classad dictionary
                   Returns: flat hash value (for hashing functions returning also lists, use `fetch2count`)
                            if None, will not be counted

    Returns:
        dict: Dictionary with a count of the hash values returned.
    """
    data_list = sorted(hash_func(v) for v in list(data.values()))
    count = {key: len(list(group)) for key, group in groupby([i for i in data_list if i is not None])}
    return count


def fetch2list(data, hash_func):
    """Convert data into a nested dictionary structure based on hash values.

    This function takes a dictionary of data and a hash function, and creates a nested dictionary structure
    based on the hash values returned by the hash function. It uses the hash values to organize the data into
    lists or dictionaries within the nested structure.

    Args:
        data (dict): The input data to be converted into a nested dictionary. The result from a `fetch()`.
        hash_func (function or None): The hash function used to generate hash values from data elements.
                        One argument: classad dictionary
                        Returns: hash value
                            - if None, will not be counted
                            - if a list, all elements will be used

    Returns:
        dict: Nested dictionary structure containing the converted data.
              It is a dictionary of hash values. Elements are lists of keys (or more dictionaries if hash returns lists)
    """
    return_list = {}

    # Iterate through each key in the data dictionary
    for k in list(data.keys()):
        el = data[k]  # Get the data element associated with the current key

        # Calculate the hash value using the provided hash function
        hid = hash_func(el)

        # Skip this element if the hash function returns None
        if hid is None:
            continue

        # Initialize a pointer to the current level of the return dictionary
        lel = return_list

        # Check if the element/hash value is a list
        if isinstance(hid, list):
            # Traverse the nested dictionary structure based on the hash values
            for h in hid[:-1]:
                if h not in lel:
                    lel[h] = {}
                lel = lel[h]

            # Use the last hash value to access the final level of the nested dictionary
            hid = hid[-1]

        # Check if the hash value already exists in the current level of the return dictionary
        if hid in lel:
            # If the hash value already exists, append the current key to the corresponding list
            list_el = lel[hid].append[k]
        else:
            # If the hash value does not exist, create a new list with the current key
            list_el = [k]

        # Update the nested dictionary with the new list
        lel[hid] = list_el

    return return_list


def addDict(base_dict, new_dict):
    """Recursively add two dictionaries.
    Do it in place, using the first one.

    Args:
        base_dict (dict): First dictionary.
        new_dict (dict): Dictionary to be added.
    """
    for k in new_dict:
        new_el = new_dict[k]
        if k not in base_dict:
            # nothing there?, just copy
            base_dict[k] = new_el
        else:
            if isinstance(new_el, dict):
                # another dictionary, recourse
                addDict(base_dict[k], new_el)
            else:
                base_dict[k] += new_el


################################################################################
# Functions to convert existing data type to their bindings friendly equivalent
################################################################################


def resource_str_to_py_adtype(resource_str):
    """Given the resource string return equivalent classad type"""

    adtype = resource_str
    if USE_HTCONDOR_PYTHON_BINDINGS:
        adtypes = {
            "-any": htcondor.AdTypes.Any,
            "-collector": htcondor.AdTypes.Collector,
            "-generic": htcondor.AdTypes.Generic,
            "-grid": htcondor.AdTypes.Grid,
            "-had": htcondor.AdTypes.HAD,
            "-license": htcondor.AdTypes.License,
            "-master": htcondor.AdTypes.Master,
            "-negotiator": htcondor.AdTypes.Negotiator,
            "-schedd": htcondor.AdTypes.Schedd,
            "-startd": htcondor.AdTypes.Startd,
            "-submitter": htcondor.AdTypes.Submitter,
        }
        # Default to startd ads, even if resource_str is empty
        adtype = adtypes.get(resource_str, htcondor.AdTypes.Startd)
    return adtype


def bindings_friendly_constraint(constraint):
    """Convert the constraint to format that can be used with python bindings."""
    if constraint is None:
        return True
    return constraint


def bindings_friendly_attrs(format_list):
    """Convert the format_list into attrs that can be used with Python bindings.
    Python bindings should take care of the typing.
    """
    if format_list is not None:
        return [f[0] for f in format_list]
    return []


################################################################################
# TODO: Following code is never used. Maybe we should yank it off in future
#       during code cleanup.
################################################################################


class SummarizeMulti:
    """Class to summarize multiple queries.

    This class aggregates the results of multiple queries into a single summary. It provides methods to count
    occurrences based on specified constraints and hash functions.

    Args:
        queries (list): A list of query objects to be summarized.
        hash_func (function, optional): The hash function used for summarization. Defaults to a function that
            always returns 1.

    Attributes:
        counts (list): A list containing the results of individual queries.
    """

    def __init__(self, queries, hash_func=lambda x: 1):
        """Initializes the SummarizeMulti object.

        Args:
            queries (list): A list of query objects to be summarized.
            hash_func (function, optional): The hash function used for summarization. Defaults to a function
                                            that always returns 1.
        """
        self.counts = []
        for query in queries:
            self.counts.append(self.count(query, hash_func))
        self.hash_func = hash_func

    def count(self, constraint=None, hash_func=None):
        """Count occurrences based on specified constraints and hash functions.

        This method counts occurrences based on the specified constraints and hash functions for all queries
        stored in the SummarizeMulti object.

        Args:
            constraint (str, optional): A string representing the query constraint. Defaults to None.
            hash_func (function, optional): The hash function used for counting. Defaults to None.

        Returns:
            dict: A dictionary containing the count of occurrences.
        """
        out = {}

        for c in self.counts:
            data = c.count(constraint, hash_func)
            addDict(out, data)

        return out

    def countStored(self, constraint_func=None, hash_func=None):
        """Count occurrences using stored data and specified constraints and hash functions.

        This method counts occurrences using the stored data and specified constraints and hash functions
        for all queries stored in the SummarizeMulti object.

        Args:
            constraint_func (function, optional): A function representing the constraint. Defaults to None.
            hash_func (function, optional): The hash function used for counting. Defaults to None.

        Returns:
            dict: A dictionary containing the count of occurrences.
        """
        out = {}

        for c in self.counts:
            data = c.countStored(constraint_func, hash_func)
            addDict(out, data)

        return out


# condor_q, where we have only one ProcId x ClusterId
class CondorQLite(CondorQuery):
    """Class for querying a Condor pool with simplified functionality.

    This class extends the functionality of the CondorQuery class to provide simplified querying of a Condor pool.
    It is designed to handle basic query operations with a focus on ease of use and reduced complexity.

    Args:
        schedd_name (str, optional): The name of the schedd. Defaults to None.
        pool_name (str, optional): The name of the pool. Defaults to None.
        security_obj (object, optional): The security object for authentication. Defaults to None.
        schedd_lookup_cache (object, optional): The cache object for storing schedd lookup data. Defaults to
            local_schedd_cache.

    Attributes:
        schedd_name (str): The name of the schedd.
        pool_name (str): The name of the pool.
        security_obj (object): The security object for authentication.
        schedd_lookup_cache (object): The cache object for storing schedd lookup data.
    """

    def __init__(self, schedd_name=None, pool_name=None, security_obj=None, schedd_lookup_cache=local_schedd_cache):
        """Initializes the CondorQLite object.

        Args:
            schedd_name (str, optional): The name of the schedd. Defaults to None.
            pool_name (str, optional): The name of the pool. Defaults to None.
            security_obj (object, optional): The security object for authentication. Defaults to None.
            schedd_lookup_cache (object, optional): The cache object for storing schedd lookup data. Defaults to
                local_schedd_cache.
        """
        self.schedd_name = schedd_name

        if schedd_lookup_cache is None:
            schedd_lookup_cache = NoneScheddCache()

        schedd_str, env = schedd_lookup_cache.getScheddId(schedd_name, pool_name)

        CondorQuery.__init__(self, "condor_q", schedd_str, "ClusterId", pool_name, security_obj, env)

    def fetch(self, constraint=None, format_list=None):
        """Fetches data from the Condor pool.

        This method fetches data from the Condor pool based on the specified constraint and format list.

        Args:
            constraint (str, optional): The constraint for filtering the query results. Defaults to None.
            format_list (list, optional): The list of attributes and their types for formatting the query results.
                Defaults to None.

        Returns:
            dict: A dictionary containing the query results.
        """
        if format_list is not None:
            # check that ClusterId is present, and if not add it
            format_list = complete_format_list(format_list, [("ClusterId", "i")])
        return CondorQuery.fetch(self, constraint=constraint, format_list=format_list)
