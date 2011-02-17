#!/usr/bin/env python

import sys,os.path,string,time,stat,shutil, getpass
import pwd
import socket
import re

#--------------------------
class WMSerror(Exception):
  pass 
#--------------------------
def logit(message):
   print message
#--------------------------
def logerr(message):
   logit("ERROR: %s" % message)
   raise WMSerror(Exception)
#--------------------------
def logwarn(message):
   logit("Warning: %s" % message)

#--------------------------
def write_file(mode,perm,filename,data):
  if mode == "w":
    logit("Creating: %s" % filename)
    make_backup(filename)
  elif mode == "a":
    logit("Appending to file: %s" % filename)
  else:
    logerr("Internal error in accessing write_file method: Invalid mode(%s)" % mode)
  fd = open(filename,mode)
  try:
    try:    
      fd.write(data)
    except Exception,e:
      logerr("Problem writing %s: %s" % (filename,e))
  finally:
    fd.close()
  os.chmod(filename,perm) 

#--------------------------
def make_directory(dirname,owner,perm,empty_required=True):
  ## logit("... checking directory: %s" % dirname)
  if os.path.isdir(dirname):
    if not_writeable(dirname):
      logerr("Directory (%s) exists but is not writable by user %s" % (dirname,owner))
    if not empty_required:
      return # we done.. does not have to be empty

    if len(os.listdir(dirname)) == 0:
      return  # we done.. its empty

    if ask_yn( "... directory (%s) already exists and must be empty.\n... can the contents be removed (y/n>" % dirname) == "n":
      logerr("Terminating at your request")
    #if not_writeable(os.path.dirname(dirname)): #not removing in case correct
    if not_writeable(dirname):
      logerr("Cannot empty %s because of permissions/ownership of parent dir" % dirname)
    remove_dir_contents(dirname)
    return  # we done.. all is ok

  #-- create it but check entire path ---
  ## ask_continue("... directory does not exist. Is it OK to create it")
  logit("... creating directory: %s" % dirname)
  dirs = [dirname,]  # directories we need to create
  dir = dirname
  while dir <> "/":
    parent_dir = os.path.dirname(dir)
    if os.path.isdir(parent_dir):
      break
    dirs.append(parent_dir)
    dir = parent_dir
  dirs.reverse()
  for dir in dirs:
    if not_writeable(parent_dir):
      logerr("Cannot create %s because of permissions/ownership\n       of parent dir(%s)" % (dirname,parent_dir))
    try:
      os.makedirs(dir)
      os.chmod(dir,perm)
      uid = pwd.getpwnam(owner)[2]
      gid = pwd.getpwnam(owner)[3]
      os.chown(dir,uid,gid)
    except:
      logit("... trying to create directory: %s" % dirname)
      logerr("Failed to create or set permissions/ownership(%s) on directory: %s" % (owner,dir))
    logit( "... directory created: %s" % dir)
  return
  
#--------------------------
def remove_dir_contents(dirname):
  err = os.system("rm -rf %s/*" % dirname)
  if err != 0:
    logerr("Problem deleting files in %s" % dirname)
  logit("Files in %s  deleted\n" % dirname)
  
#--------------------------
def not_writeable(dirname):
  test_fname=os.path.join(dirname,"test.txt")
  try:
    fd=open(test_fname,"w")
    fd.close()
    os.unlink(test_fname)
  except:
    return True
  return False

#--------------------------
def has_permissions(dir,level,perms):
  result = True
  mode =  stat.S_IMODE(os.lstat(dir)[stat.ST_MODE])
  for perm in perms:
    if mode & getattr(stat,"S_I"+perm+level):
      continue
    result = False
    break
  return result

#--------------------------
def remove_dir_path(dirname):
  if os.path.isdir(dirname):
    shutil.rmtree(dirname)
    logit( "... directory removed: %s" % dirname)
  else:
    logit( "... directory does not exist: %s" % dirname)

#--------------------------
def make_backup(filename):
  if os.path.isfile(filename):
    backup = "%s.%s" % (filename,time_suffix())
    shutil.copy2(filename,backup)
    logit( "... backup of %s created: %s" % (filename,backup))
  #else:
  #  logit( "... no backup required, file does not exist: %s" % (filename))

#--------------------------
def time_suffix():
  return time.strftime("%Y%m%d_%H%M%S",time.localtime())


#--------------------------------------
def run_script(script):
  """ Runs a script using os-system. """
  logit("... running: %s" % script)
  err = os.system(script)
  if err != 0:
    logerr("Script failed with non-zero return code")


#--------------------------------------
def cron_append(lines,tmp_dir='/tmp'):
  """ Append a line to the crontab for a user."""
  logit("\n... adding %i lines to %s's crontab" % (len(lines),getpass.getuser()))
  tmp_fname="%s/tmp_%s_%s.tmp"%(tmp_dir,os.getpid(),time.time())
  try:
    os.system("crontab -l >%s"%tmp_fname)
    fd=open(tmp_fname,'a')
    try:
      for line in lines:
        fd.writelines(line)
    finally:
      fd.close()
    os.system("cat %s" % tmp_fname)
    os.system("crontab %s" % tmp_fname)
  finally:
    if os.path.isfile(tmp_fname):
      os.unlink(tmp_fname)
  logit("\n... %s's crontab updated" % (getpass.getuser()))

#--------------------------------------
def module_exists(module_name):
  err = os.system("python -c 'import %s' >/dev/null 2>&1" % module_name)
  if err != 0:
    return False
  return True

#--------------------------------
def validate_email(email):
  logit("... validating condor_email_address: %s" % email)
  if email.find('@')<0:
    logerr("Invalid email address (%s)" % (email))

#--------------------------------
def validate_install_location(dir):
  logit("... validating install_location: %s" % dir)
  install_user = pwd.getpwuid(os.getuid())[0]
  make_directory(dir,install_user,0755,empty_required=True)

#--------------------------------
def ask_yn(question):
  while 1:
    yn = raw_input("%s? (y/n): " % (question))
    if yn.strip() == "y" or yn.strip() == "n":
      break
    logit("... just 'y' or 'n' please")
  return yn.strip()

#--------------------------------
def ask_continue(question):
  while 1:
    yn = raw_input("%s? (y/n): " % (question))
    if yn.strip() == "y" or yn.strip() == "n":
      break
    logit("... just 'y' or 'n' please")
  if yn.strip() == "n":
    raise KeyboardInterrupt

#--------------------------------
def validate_hostname(node,additional_msg=""):
  logit("... validating hostname: %s" % node)
  if node <> socket.getfqdn():
    logerr("""The hostname option (%(hostname)s) shows a different host. 
      This is %(thishost)s.
      %(msg)s """ % { "hostname" : node,
                      "thishost" : socket.getfqdn(),
                      "msg"      : additional_msg,})

#--------------------------------
def validate_user(user):
  logit("... validating username: %s" % user)
  try:
    x = pwd.getpwnam(user)
  except:
    logerr("User account (%s) does not exist. Either create it or specify a different user." % (user))

#--------------------------------
def validate_installer_user(user):
  logit("... validating installer_user: %s" % user)
  install_user = pwd.getpwuid(os.getuid())[0]
  if user <> install_user:
    logerr("You are installing as user(%s).\n       The ini file says it should be user(%s)." % (install_user,user))

#--------------------------------
def validate_gsi_for_proxy(dn_to_validate,proxy):
  install_user = pwd.getpwuid(os.getuid())[0]
  #-- check proxy ---
  logit("... validating x509_proxy: %s" % proxy)
  if not os.path.isfile(proxy):
    logerr("""x509_proxy (%(proxy)s)
not found or has wrong permissions/ownership.""" % \
  {  "proxy"  :  proxy,
     "owner" : install_user,})
  #-- check dn ---
  logit("... validating x509_gsi_dn: %s" % dn_to_validate)
  dn_in_file = get_gsi_dn("proxy",proxy)
  if dn_in_file <> dn_to_validate:
    logerr("""The DN of the x509_proxy option does not match the x509_gsi_dn 
option value in your ini file:
  x509_gsi_dn: %(dn_to_validate)s
x509_proxy DN: %(dn_in_file)s
This may cause a problem in other services.
You should reinstall any services already complete.""" % \
    { "dn_in_file"     : dn_in_file,
      "dn_to_validate" : dn_to_validate,})

#--------------------------------
def validate_gsi_for_cert(dn_to_validate,cert,key):
  install_user = pwd.getpwuid(os.getuid())[0]
  #-- check cert ---
  logit("... validating x509_cert: %s" % cert)
  if not os.path.isfile(cert):
    logerr("""x509_cert (%(cert)s)
not found or has wrong permissions/ownership.""" % \
       {  "cert"  :  cert, 
          "owner" : install_user,})
  #-- check key ---
  logit("... validating x509_key: %s" % key)
  if not os.path.isfile(key):
    logerr("""x509_key (%(key)s)
not found or has wrong permissions/ownership.""" % \
        {  "key"  :  key, 
          "owner" : install_user,})
  #-- check dn ---
  logit("... validating x509_gsi_dn: %s" % dn_to_validate)
  dn_in_file = get_gsi_dn("cert",cert)
  if dn_in_file <> dn_to_validate:
    logerr("""The DN of the x509_cert option does not match the x509_gsi_dn 
option value in your ini file:
  x509_gsi_dn: %(dn_to_validate)s
 x509_cert DN: %(dn_in_file)s
This may cause a problem in other services.
You should reinstall any services already complete.""" % \
    { "dn_in_file"     : dn_in_file, 
      "dn_to_validate" : dn_to_validate,})

#--------------------------------
def get_gsi_dn(type,filename):
  """ Returns the 'identity' of the user for a certificate
      or proxy.  Using openssl, If it is a proxy, use the -issuer argument.
      If a certificate, use the -subject argument.
  """
  install_user = pwd.getpwuid(os.getuid())[0]
  if type == "proxy":
    arg = "-issuer"
    if not os.path.isfile(filename):
      logerr("Proxy (%s)\nnot found or has wrong permissions/ownership.\nThe proxy has to be owned by %s and have 600 permissions" % (filename,install_user))
  elif type == "cert":
    arg = "-subject"
  else:
    logerr("Invalid type (%s). Must be either 'cert' or 'proxy'." % type)

  if not os.path.isfile(filename):
    logerr("%s '%s' not found" % (type,filename))

  if os.stat(filename).st_uid <> os.getuid():
    logerr("The %s specified (%s)\nhas to be owned by %s user" % (type,filename,install_user))

  #-- read the cert/proxy --
  dn_fd   = os.popen("openssl x509 %s -noout -in %s 2>/dev/null" % (arg,filename))
  dn_blob = dn_fd.read()
  err = dn_fd.close()
  if err != None:
    logerr("Failed to read %s from %s" % (arg,filename))
  #-- parse out the DN --
  i = dn_blob.find("= ")
  if i < 0:
    logerr("Failed to extract DN from %s '%s'." % (arg,filename))
  dn_blob = dn_blob[i+2:] # remove part before identity
  my_dn   = dn_blob[:dn_blob.find('\n')] # keep only the part until the newline
  return my_dn

#----------------------------
def mapfile_entry(dn,name):
  if len(dn) == 0 or len(name) == 0:
    return ""
  return """GSI "^%(dn)s$" %(name)s
""" % { "dn" : re.escape(dn), "name" : name,}

#----------------------------
def not_an_integer(value):
  try:
    nbr = int(value)
  except:
    return True
  return False

#----------------------------
def url_is_valid(url):
  try:
    ress_ip=socket.gethostbyname(url)
  except:
    return False
  return True

#----------------------------
def wget_is_valid(location):
  err = os.system("wget --quiet --spider %s" % location)
  if err != 0:
    return False
  return True


#------------------
def indent(level):
  indent = ""
  while len(indent) < (level * 2):
    indent = indent + "  "
  return indent

#------------------
def start_service(glidein_src, service, inifile):
  """ Generic method for asking if service is to be started and 
      starting it if requested. 
  """
  argDict = { "WMSCollector"   : "wmscollector",
              "Factory"        : "factory",
              "UserCollector"  : "usercollector",
              "Submit"         : "submit",
              "VOFrontend"     : "vofrontend",
            }
  cmd ="%(glidein_src)s/install/manage-glideins --start %(service)s --ini %(inifile)s" % \
           { "inifile" : inifile,
             "service" : argDict[service],
             "glidein_src" : glidein_src, 
           }
  os.system("sleep 3")
  logit("")
  logit("You will need to have the %(service)s service running if you intend\nto install the other glideinWMS components." % { "service" : service })
  yn = ask_yn("... would you like to start it now")
  if yn == "y":
     run_script(cmd)
  else:
    logit("\nTo start the %(service)s you can run:\n %(cmd)s" % \
           { "cmd"     : cmd,
             "service" : service,
           })

#######################################
if __name__ == '__main__':
  print "Starting some tests"
  #ans = ask_continue("kldsjfklj")
  #print ans
  #sys.exit(0)
  try:
    print "Testing make_directory"
    owner = pwd.getpwuid(os.getuid())[0]
    perm = 0755
    testdir = "/opt/testdir/testdir1/testdir2/testdir3"
    print "... %s" % testdir
    make_directory(testdir,owner,perm,empty_required=True)
    if not os.path.isdir(testdir):
      print "FAILED"
    print "PASSED"
    os.rmdir(testdir)

    print "Testing make_backup"
    make_directory(testdir,owner,perm,empty_required=True)
    filename = "%s/%s" % (testdir,__file__)
    shutil.copy(__file__,filename)
    make_backup(filename)
    os.system("rm -f %s*" % filename)
    os.rmdir(testdir)
    os.rmdir(os.path.dirname(testdir))
    print "... PASSED"

  except Exception,e:
    print "FAILED test"
    print e
    sys.exit(1)
  print "PASSED all tests"
  sys.exit(0)






