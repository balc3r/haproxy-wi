# -*- coding: utf-8 -*-"
import cgi
import os, sys
import paramiko
import http.cookies
from paramiko import SSHClient
from datetime import datetime
from pytz import timezone
from configparser import ConfigParser, ExtendedInterpolation

form = cgi.FieldStorage()
serv = form.getvalue('serv')

def get_app_dir():
	d = sys.path[0]
	d = d.split('/')[-1]
	if d == "app":
		return sys.path[0]		
	else:
		return os.path.dirname(sys.path[0])		

def get_config_var(sec, var):
	try:
		path_config = get_app_dir()+"/haproxy-webintarface.config"
		config = ConfigParser(interpolation=ExtendedInterpolation())
		config.read(path_config)
	except:
		print('Content-type: text/html\n')
		print('<center><div class="alert alert-danger">Check the config file, whether it exists and the path. Must be: app/haproxy-webintarface.config</div>')

	try:
		var = config.get(sec, var)
		return var
	except:
		print('Content-type: text/html\n')
		print('<center><div class="alert alert-danger">Check the config file. Presence section %s and parameter %s</div>' % (sec, var))
					
def get_data(type):
	now_utc = datetime.now(timezone(get_config_var('main', 'time_zone')))
	if type == 'config':
		fmt = "%Y-%m-%d.%H:%M:%S"
	if type == 'logs':
		fmt = '%Y%m%d'
	if type == "date_in_log":
		fmt = "%b %d %H:%M:%S"
		
	return now_utc.strftime(fmt)
			
def logging(serv, action, **kwargs):
	import sql
	log_path = get_config_var('main', 'log_path')
	try:
		IP = cgi.escape(os.environ["REMOTE_ADDR"])
		cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
		user_uuid = cookie.get('uuid')
		login = sql.get_user_name_by_uuid(user_uuid.value)
	except:
		pass
		
	if kwargs.get('alerting') == 1:
		mess = get_data('date_in_log') + action + "\n"
		log = open(log_path + "/checker-"+get_data('logs')+".log", "a")
	elif kwargs.get('metrics') == 1:
		mess = get_data('date_in_log') + action + "\n"
		log = open(log_path + "/metrics-"+get_data('logs')+".log", "a")
	else:
		mess = get_data('date_in_log') + " from " + IP + " user: " + login + " " + action + " for: " + serv + "\n"
		log = open(log_path + "/config_edit-"+get_data('logs')+".log", "a")
			
	try:				
		log.write(mess)
		log.close
	except IOError:
		print('<center><div class="alert alert-danger">Can\'t read write log. Please chech log_path in config</div></center>')
		pass
	
def telegram_send_mess(mess, **kwargs):
	import telebot
	from telebot import apihelper
	import sql
	
	telegrams = sql.get_telegram_by_ip(kwargs.get('ip'))
	
	for telegram in telegrams:
		token_bot = telegram[1]
		channel_name = telegram[2]
		
	proxy = get_config_var('main', 'proxy')
	
	if proxy is not None:
		apihelper.proxy = {'https': proxy}
	try:
		bot = telebot.TeleBot(token=token_bot)
		bot.send_message(chat_id=channel_name, text=mess)
	except:
		print("Fatal: Can't send message. Add Telegram chanel before use alerting at this servers group")
		sys.exit()
	
def check_login(**kwargs):
	import sql
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_uuid = cookie.get('uuid')
	ref = os.environ.get("SCRIPT_NAME")

	sql.delete_old_uuid()
	
	if user_uuid is not None:
		sql.update_last_act_user(user_uuid.value)
		if sql.get_user_name_by_uuid(user_uuid.value) is None:
			print('<meta http-equiv="refresh" content="0; url=login.py?ref=%s">' % ref)
	else:
		print('<meta http-equiv="refresh" content="0; url=login.py?ref=%s">' % ref)
				
def is_admin(**kwargs):
	import sql
	cookie = http.cookies.SimpleCookie(os.environ.get("HTTP_COOKIE"))
	user_id = cookie.get('uuid')
	try:
		role = sql.get_user_role_by_uuid(user_id.value)
	except:
		role = 3
		pass
	level = kwargs.get("level")
		
	if level is None:
		level = 1
		
	try:
		if role <= level:
			return True
		else:
			return False
	except:
		return False
		pass

def page_for_admin(**kwargs):
	give_level = kwargs.get("level")
	
	if give_level is None:
		give_level = 1
	
	if not is_admin(level = give_level):
		print('<center><h3 style="color: red">How did you get here?! O_o You do not have need permissions</h>')
		print('<meta http-equiv="refresh" content="10; url=/">')
		import sys
		sys.exit()
				
def ssh_connect(serv, **kwargs):
	import sql
	fullpath = get_config_var('main', 'fullpath')
	for sshs in sql.select_ssh(serv=serv):
		ssh_enable = sshs[3]
		ssh_user_name = sshs[4]
		ssh_user_password = sshs[5]
		ssh_key_name = fullpath+'/keys/%s.pem' % sshs[2]
	ssh = SSHClient()
	ssh.load_system_host_keys()
	ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	try:
		if ssh_enable == 1:
			k = paramiko.RSAKey.from_private_key_file(ssh_key_name)
			ssh.connect(hostname = serv, username = ssh_user_name, pkey = k )
		else:
			ssh.connect(hostname = serv, username = ssh_user_name, password = ssh_user_password)
		if kwargs.get('check'):
			return True
		else:
			return ssh
	except paramiko.AuthenticationException:
		if kwargs.get('check'):
			print('<div class="alert alert-danger">Authentication failed, please verify your credentials</div>')
			return False
		else:
			return 'Authentication failed, please verify your credentials'
			pass
	except paramiko.SSHException as sshException:
		if kwargs.get('check'):
			print('<div class="alert alert-danger">Unable to establish SSH connection: %s </div>' % sshException)
			return False
		else:
			return 'Unable to establish SSH connection: %s ' % sshException
			pass
	except paramiko.BadHostKeyException as badHostKeyException:
		if kwargs.get('check'):
			print('<div class="alert alert-danger">Unable to verify server\'s host key: %s </div>' % badHostKeyException)	
			return False
		else:
			return 'Unable to verify server\'s host key: %s ' % badHostKeyException
			pass
	except Exception as e:
		if e == "No such file or directory":
			if kwargs.get('check'):
				print('<div class="alert alert-danger">{}. Check ssh key</div>'.format(e))	
			else:
				return '{}. Check ssh key'.format(e)
				pass
		elif e == "Invalid argument":
			if kwargs.get('check'):
				print('<div class="alert alert-danger">Check the IP of the new server</div>')
			else:
				error = 'Check the IP of the new server'
				pass
		else:
			if kwargs.get('check'):
				print('<div class="alert alert-danger">{}</div>'.format(e))	
			else:
				error = e	
				pass
		if kwargs.get('check'):
			return False
		else:
			return error

def get_config(serv, cfg, **kwargs):
	error = ""
	if kwargs.get("keepalived"):
		config_path = "/etc/keepalived/keepalived.conf"
	else:
		config_path = get_config_var('haproxy', 'haproxy_config_path')
		
	ssh = ssh_connect(serv)
	try:
		sftp = ssh.open_sftp()
		sftp.get(config_path, cfg)
		sftp.close()
		ssh.close()
	except Exception as e:
		ssh += str(e)
		return ssh
	
def show_config(cfg):
	print('<div style="margin-left: 16%" class="configShow">')
	try:
		conf = open(cfg, "r")
	except IOError:
		print('<div class="alert alert-danger">Can\'t read import config file</div>')
	i = 0
	for line in conf:
		i = i + 1
		if not line.find("global"):
			print('<span class="param">' + line + '</span><div>')
			continue
		if not line.find("defaults"):
			print('</div><span class="param">' + line + '</span><div>')
			continue
		if not line.find("listen"):
			print('</div><span class="param">' + line + '</span><div>')
			continue
		if not line.find("frontend"):
			print('</div><span class="param">' + line + '</span><div>')
			continue
		if not line.find("backend"):
			print('</div><span class="param">' + line + '</span><div>')
			continue
		if "acl" in line or "option" in line or "server" in line:
			if "timeout" not in line and "default-server" not in line and "#use_backend" not in line:
				print('<span class="paramInSec"><span class="numRow">')
				print(i)
				print('</span>' + line + '</span><br />')
				continue
		if "#" in line:
			print('<span class="comment"><span class="numRow">')
			print(i)
			print(line + '</span></span><br />')
			continue	
		if line.__len__() < 1:
			print('</div>')
		if line.__len__() > 1:
			print('<span class="configLine"><span class="numRow">')
			print(i)
			print('</span>' + line + '</span><br />')					
	print('</div></div>')
	conf.close

def diff_config(oldcfg, cfg):
	import subprocess 
	log_path = get_config_var('main', 'log_path')
	diff = ""
	date = get_data('date_in_log') 
	cmd="/bin/diff -ub %s %s" % (oldcfg, cfg)
	
	output, stderr = subprocess_execute(cmd)
	
	for line in output:
		diff += date + " " + line + "\n"
	try:		
		log = open(log_path + "/config_edit-"+get_data('logs')+".log", "a")
		log.write(diff)
		log.close
	except IOError:
		print('<center><div class="alert alert-danger">Can\'t read write change to log. %s</div></center>' % stderr)
		pass
		
def install_haproxy(serv, **kwargs):
	script = "install_haproxy.sh"
	tmp_config_path = get_config_var('haproxy', 'tmp_config_path')
	proxy = get_config_var('main', 'proxy')
	os.system("cp scripts/%s ." % script)
	if proxy is not None:
		proxy_serv = proxy
	else:
		proxy_serv = ""
	commands = [ "chmod +x "+tmp_config_path+script+" && " +tmp_config_path+"/"+script +" " + proxy_serv]
	
	upload(serv, tmp_config_path, script)	
	ssh_command(serv, commands)
	
	if kwargs.get('syn_flood') == "1":
		syn_flood_protect(serv)
	
	os.system("rm -f %s" % script)
	
def syn_flood_protect(serv, **kwargs):
	script = "syn_flood_protect.sh"
	tmp_config_path = get_config_var('haproxy', 'tmp_config_path')
	
	if kwargs.get('enable') == "0":
		enable = "disable"
	else:
		enable = "enable"

	os.system("cp scripts/%s ." % script)
	
	commands = [ "chmod +x "+tmp_config_path+script, tmp_config_path+script+ " "+enable ]
	
	upload(serv, tmp_config_path, script)	
	ssh_command(serv, commands)
	
	os.system("rm -f %s" % script)
	
def upload(serv, path, file, **kwargs):
	full_path = path + file
	
	try:
		ssh = ssh_connect(serv)
	except Exception as e:
		print('<div class="alert alert-danger">Connect fail: %s</div>' % e)
	try:
		sftp = ssh.open_sftp()
		file = sftp.put(file, full_path)
		sftp.close()
		ssh.close()
	except Exception as e:
		print('<div class="alert alert-danger">Upload fail: %s</div>' % e)
	
def upload_and_restart(serv, cfg, **kwargs):
	tmp_file = get_config_var('haproxy', 'tmp_config_path') + "/" + get_data('config') + ".cfg"
	error = ""
	
	try:
		os.system("dos2unix "+cfg)
	except OSError:
		return 'Please install dos2unix' 
		pass
		
	try:
		ssh = ssh_connect(serv)
	except:
		return 'Connect fail'
	sftp = ssh.open_sftp()
	sftp.put(cfg, tmp_file)
	sftp.close()
	if kwargs.get("keepalived") == 1:
		if kwargs.get("just_save") == "save":
			commands = [ "sudo mv -f " + tmp_file + " /etc/keepalived/keepalived.conf" ]
		else:
			commands = [ "sudo mv -f " + tmp_file + " /etc/keepalived/keepalived.conf", "sudo systemctl restart keepalived" ]
	else:
		if kwargs.get("just_save") == "save":
			commands = [ "sudo /sbin/haproxy  -q -c -f " + tmp_file + "&& sudo mv -f " + tmp_file + " " + get_config_var('haproxy', 'haproxy_config_path') ]
		else:
			commands = [ "sudo /sbin/haproxy  -q -c -f " + tmp_file + "&& sudo mv -f " + tmp_file + " " + get_config_var('haproxy', 'haproxy_config_path') + " && sudo " + get_config_var('haproxy', 'restart_command') ]	
		try:
			if get_config_var('haproxy', 'firewall_enable') == "1":
				commands.extend(open_port_firewalld(cfg))
		except:
			return 'Please check the config for the presence of the parameter - "firewall_enable". Mast be: "0" or "1". Firewalld configure not working now'
			
	for command in commands:
		stdin, stdout, stderr = ssh.exec_command(command)

	return stderr.read()
	ssh.close()
		
def open_port_firewalld(cfg):
	try:
		conf = open(cfg, "r")
	except IOError:
		print('<div class="alert alert-danger">Can\'t read export config file</div>')
	
	firewalld_commands = []
	
	for line in conf:
		if "bind" in line:
			bind = line.split(":")
			bind[1] = bind[1].strip(' ')
			bind = bind[1].split("ssl")
			bind = bind[0].strip(' \t\n\r')
			firewalld_commands.append('sudo firewall-cmd --zone=public --add-port=%s/tcp --permanent' % bind)
				
	firewalld_commands.append('sudo firewall-cmd --reload')
	return firewalld_commands
	
def check_haproxy_config(serv):
	commands = [ "/sbin/haproxy  -q -c -f %s" % get_config_var('haproxy', 'haproxy_config_path') ]
	ssh = ssh_connect(serv)
	for command in commands:
		stdin , stdout, stderr = ssh.exec_command(command)
		if not stderr.read():
			return True
		else:
			return False
	ssh.close()
	
def compare(stdout):
	i = 0
	minus = 0
	plus = 0
	total_change = 0
	
	print('</center><div class="out">')
	print('<div class="diff">')
		
	for line in stdout:
		i = i + 1

		if i is 1:
			print('<div class="diffHead">' + line + '<br />')
		elif i is 2:
			print(line + '</div>')
		elif line.find("-") == 0 and i is not 1:
			print('<div class="lineDiffMinus">' + line + '</div>')
			minus = minus + 1
		elif line.find("+") == 0 and i is not 2:
			print('<div class="lineDiffPlus">' + line + '</div>')	
			plus = plus + 1					
		elif line.find("@") == 0:
			print('<div class="lineDog">' + line + '</div>')
		else:
			print('<div class="lineDiff">' + line + '</div>')				
			
		total_change = minus + plus
	print('<div class="diffHead">Total change: %s, additions: %s & deletions: %s </div>' % (total_change, minus, plus))	
	print('</div></div>')
		
def show_log(stdout):
	i = 0
	for line in stdout:
		i = i + 1
		if i % 2 == 0: 
			print('<div class="line3">' + escape_html(line) + '</div>')
		else:
			print('<div class="line">' + escape_html(line) + '</div>')
			
def show_ip(stdout):
	for line in stdout:
		print(line)
		
def server_status(stdout):	
	proc_count = ""
	
	for line in stdout:
		if "Ncat: Connection refused." not in line:
			for k in line:
				proc_count = k.split(":")[1]
		else:
			proc_count = 0
	return proc_count		

def ssh_command(serv, commands, **kwargs):
	ssh = ssh_connect(serv)
		  
	for command in commands:
		try:
			stdin, stdout, stderr = ssh.exec_command(command)
		except:
			continue
				
		if kwargs.get("ip") == "1":
			show_ip(stdout)
		elif kwargs.get("compare") == "1":
			compare(stdout)
		elif kwargs.get("show_log") == "1":
			show_log(stdout)
		elif kwargs.get("server_status") == "1":
			server_status(stdout)
		else:
			return stdout.read().decode(encoding='UTF-8')
			
		print(stderr.read().decode(encoding='UTF-8'))
	try:	
		ssh.close()
	except:
		print(ssh)
		pass

def escape_html(text):
	return cgi.escape(text, quote=True)
	
def subprocess_execute(cmd):
	import subprocess 
	p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
	stdout, stderr = p.communicate()
	output = stdout.splitlines()
	
	return output, stderr

def show_backends(serv, **kwargs):
	import json
	cmd='echo "show backend" |nc %s 1999' % serv 
	output, stderr = subprocess_execute(cmd)
	ret = ""
	for line in output:
		if "#" in  line or "stats" in line:
			continue
		if line != "":
			back = json.dumps(line).split("\"")
			if kwargs.get('ret'):
				ret += back[1]
				ret += "<br />"
			else:
				print(back[1]+"<br>")
		
	if kwargs.get('ret'):
		return ret
		
def get_files():
	import glob
	file = set()
	return_files = set()
	hap_configs_dir = get_config_var('configs', 'haproxy_save_configs_dir')
	
	for files in glob.glob(os.path.join(hap_configs_dir,'*.cfg')):		
		file.add(files.split('/')[6])
	files = sorted(file, reverse=True)
	for file in files:
		ip = file.split("-")
		if serv == ip[0]:
			return_files.add(file)
	return sorted(return_files, reverse=True)
	