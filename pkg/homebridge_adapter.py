"""

Example addon for Candle Controller / Webthings Gateway.

This addon has the following hierarchy:

Adapter
- Device (1x)
- - Property (4x)
- API handler


"""


import os
import sys
# This helps the addon find python libraries it comes with, which are stored in the "lib" folder. The "package.sh" file will download Python libraries that are mentioned in requirements.txt and place them there.
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib')) 

import json
import time
import socket
#import datetime
#import requests  # noqa
import threading
import selectors
import subprocess

# This loads the parts of the addon.
from gateway_addon import Database, Adapter, Device, Property, APIHandler, APIResponse
# Database - needed to read from the settings database. If your addon doesn't have any settings, then you don't need this.

# Adapter. Needed if you want to provide things' to the controller.
# Device. Needed if you want to provide things' to the controller.
# Property. Needed if you want to provide things' to the controller.

# APIHandler. Needed if you want to provide an API for a UI extension.
# APIResponse. Needed if you want to provide an API for a UI extension.

# This addon does not load part from other files, but if you had a big addon you might want to split it into separate parts. For example, you could have a file called "homebridge_api_handler.py" at the same level as homebridge.py, and import it like this:
#try:
#    from .internet_radio_api_handler import *
#    print("APIHandler imported")
#except Exception as ex:
#    print("Error, unable to load APIHandler: " + str(ex))


# Not sure what this is used for, but leave it in.
_TIMEOUT = 3

# Not sure what this is used for either, but leave it in.
_CONFIG_PATHS = [
    os.path.join(os.path.expanduser('~'), '.webthings', 'config'),
]

# Not sure what this is used for either, but leave it in.
if 'WEBTHINGS_HOME' in os.environ:
    _CONFIG_PATHS.insert(0, os.path.join(os.environ['WEBTHINGS_HOME'], 'config'))




# The adapter is the top level of this hierarchy

# Adapter  <- you are here
# - Device  
# - - Property  
# - Api handler

class HomebridgeAdapter(Adapter):
    """Adapter for addon """

    def __init__(self, verbose=False):
        """
        Initialize the object.

        verbose -- whether or not to enable verbose logging
        """
        
        print("Starting adapter init")

        self.ready = False # set this to True once the init process is complete.
        self.addon_name = 'homebridge'
        
        self.name = self.__class__.__name__ # TODO: is this needed?
        Adapter.__init__(self, self.addon_name, self.addon_name, verbose=verbose)

        self.running = True

        # set up some variables
        self.DEBUG = True
        self.a_number_setting = 0
        
        # this is a completely random set of items. It is sent to the user interface through the API handler, which till turn it into a list
        self.plugins_list = [
                        {'name':'Item 1', 'value':55},
                        {'name':'Item 2', 'value':25},
                        {'name':'Item 4', 'value':200},
                        {'name':'Item 3', 'value':88},
                    ]


        # installing Homebridge
        self.hb_installed = False
        self.busy_intalling_hb = False
        self.hb_install_progress = 0

        self.launched = False
        self.hb_config_data = {}
        self.hb_name = "Candle Homebridge"
        self.qr_code_url = ""
        self.config_port = 8581
        self.ip = get_ip()
        self.hostname = socket.gethostname()

        self.setup_id = ""

        # There is a very useful variable called "user_profile" that has useful values from the controller.
        print("self.user_profile: " + str(self.user_profile))
        
        
        # This addon has a "hidden parent" itself, the manager_proxy.
        #print("self.adapter.manager_proxy: " + str(self.adapter.manager_proxy))
        
        
        # Create some path strings. These point to locations on the drive.
        self.addon_path = os.path.join(self.user_profile['addonsDir'], self.addon_name) # addonsDir points to the directory that holds all the addons (/home/pi/.webthings/addons).
        self.data_path = os.path.join(self.user_profile['dataDir'], self.addon_name)
        self.persistence_file_path = os.path.join(self.data_path, 'persistence.json') # dataDir points to the directory where the addons are allowed to store their data (/home/pi/.webthings/data)
        
        self.hb_path = os.path.join(self.data_path, "hb")
        print("self.hb_path: " + str(self.hb_path))
        self.hb_node_path = os.path.join(self.hb_path, "opt","homebridge","bin","node")
        self.hb_npm_path = os.path.join(self.hb_path, "opt","homebridge","bin","npm")
        self.hb_service_path = os.path.join(self.hb_path, "opt","homebridge","lib","node_modules","homebridge-config-ui-x","dist/bin/hb-service.js")
        self.hb_storage_path = os.path.join(self.hb_path, "var","lib","homebridge") # TODO: just make this the data root path for optimal backup support?
        self.hb_plugins_path = os.path.join(self.hb_storage_path, "node_modules") 
        self.hb_logs_file_path = os.path.join(self.hb_storage_path, "homebridge.log") 
        self.hb_config_file_path = os.path.join(self.hb_storage_path, "config.json") 
        
        print("self.hb_service_path: " + str(self.hb_service_path))
        print("self.hb_logs_file_path: " + str(self.hb_logs_file_path))
        
        
        # Create the data directory if it doesn't exist yet
        if not os.path.isdir(self.data_path):
            print("making missing data directory")
            os.mkdir(self.data_path)
            
        # Create the hb directory if it doesn't exist yet
        if not os.path.isdir(self.hb_path):
            print("making missing hb directory")
            os.mkdir(self.hb_path)
        
        # Check if homebridge is already installed
        if os.path.isfile(self.hb_service_path):
            print("Homebridge is installed")
            self.hb_installed = True
            self.hb_install_progress = 100
        
        # Clear previous log
        if os.path.isfile(self.hb_logs_file_path):
            os.system('echo "" > '  + str(self.hb_logs_file_path))
            
        
        
            
        # Get persistent data
        self.persistent_data = {}
        try:
            with open(self.persistence_file_path) as f:
                self.persistent_data = json.load(f)
                if self.DEBUG:
                    print('self.persistent_data was loaded from file: ' + str(self.persistent_data))
                    
        except:
            if self.DEBUG:
                print("Could not load persistent data (if you just installed the add-on then this is normal)")

        # 2. now that we have the persistent data (except on the first run), we allow the basic settings to override some of the values, if they are set.

        try:
            self.add_from_config()
        except Exception as ex:
            print("Error loading config: " + str(ex))

        # 3. Now we check if all the values that should exist actually do

        if 'state' not in self.persistent_data:
            self.persistent_data['state'] = False

        if 'slider' not in self.persistent_data:
            self.persistent_data['slider'] = 0
            
        if 'dropdown' not in self.persistent_data:
            self.persistent_data['dropdown'] = 'Auto'

        if 'token' not in self.persistent_data:
            self.persistent_data['token'] = "No token provided yet"

        if 'things' not in self.persistent_data:
            self.persistent_data['things'] = []


        # create list of installed plugins
        self.update_installed_plugins_list()

        # Start the API handler. This will allow the user interface to connect
        try:
            if self.DEBUG:
                print("starting api handler")
            self.api_handler = HomebridgeAPIHandler(self, verbose=True)
            if self.DEBUG:
                print("Adapter: API handler initiated")
        except Exception as e:
            if self.DEBUG:
                print("Error, failed to start API handler: " + str(e))


        # Create the thing
        try:
            pass
            # Create the device object
            #homebridge_device = HomebridgeDevice(self)
            
            # Tell the controller about the new device that was created. This will add the new device to self.devices too
            #self.handle_device_added(homebridge_device)
            
            #if self.DEBUG:
            #    print("homebridge_device created")
                
            # You can set the device to connected or disconnected. If it's in disconnected state the thing will visually be a bit more transparent.
            #self.devices['homebridge-thing'].connected = True
            #self.devices['homebridge-thing'].connected_notify(True)

        except Exception as ex:
            print("Could not create homebridge_device: " + str(ex))


        if self.hb_installed == False:
            print("INSTALLING HOMEBRIDGE")
            self.install_hb()
        else:
            print("Homebridge seems to be installed")
            self.run_hb()
        
        # Just in case any new values were created in the persistent data store, let's save if to disk
        self.save_persistent_data()
        
        # The addon is now ready
        self.ready = True 
        
        if self.DEBUG:
            print("homebridge init done")


    def add_from_config(self):
        """ This retrieves the addon settings from the controller """
        print("in add_from_config")
        try:
            database = Database(self.addon_name)
            if not database.open():
                print("Error. Could not open settings database")
                return

            config = database.load_config()
            database.close()

        except:
            print("Error. Failed to open settings database. Closing proxy.")
            self.close_proxy() # this will purposefully "crash" the addon. It will then we restarted in two seconds, in the hope that the database is no longer locked by then
            return
            
        try:
            if not config:
                print("Warning, no config.")
                return

            # Let's start by setting the user's preference about debugging, so we can use that preference to output extra debugging information
            if 'Debugging' in config:
                self.DEBUG = bool(config['Debugging'])
                if self.DEBUG:
                    print("Debugging enabled")

            if self.DEBUG:
                print(str(config)) # Print the entire config data
                
            if 'A boolean setting' in config:
                self.persistent_data['a_boolean_setting'] = bool(config['A boolean setting']) # sometime you may want the addon settings to override the persistent value
                if self.DEBUG:
                    print("A boolean setting preference was in config: " + str(self.persistent_data['a_boolean_setting']))

            if 'A number setting' in config:
                #print("-Debugging was in config")
                self.a_number_setting = int(config['A number setting'])
                if self.DEBUG:
                    print("A number setting preference was in config: " + str(self.a_number_setting))
            
            if "Homebridge name" in config:
                self.hb_name = str(config["Homebridge name"])
                if self.DEBUG:
                    print("Homebridge name preference was in config: " + str(self.hb_name))
            
            
            

        except Exception as ex:
            print("Error in add_from_config: " + str(ex))







    def install_hb(self):
        if self.busy_intalling_hb == True:
            print("Already busy installing Homebridge, aborting new install")
            return
        
        try:
            os.chdir(self.hb_path)
        
            # check if there is enough disk space
            space = shell("df -P " + str(self.user_profile['addonsDir']) + " | tail -1 | awk '{print $4}'")
            # df -P . | tail -1 | awk '{print $4}'
        
            print("free disk space: " + str(space))
        
            if len(space) == 0:
                print("Error running disk space check command")
                return
        
            if int(space) < 500000:
                print("Not enough free disk space for installation")
                self.hb_install_progress = -2
                self.busy_intalling_hb = False
                return
            else:
                print("Enough disk space available")
            
            
            print("Starting Homebridge install")
            self.busy_intalling_hb == True
        
            self.hb_install_progress = 2
        
        
        
            os.system('curl -sSfL https://repo.homebridge.io/KEY.gpg | sudo gpg --dearmor | sudo tee /usr/share/keyrings/homebridge.gpg  > /dev/null')
            self.hb_install_progress = 4
        
            os.system('echo "deb [signed-by=/usr/share/keyrings/homebridge.gpg] https://repo.homebridge.io stable main" | sudo tee /etc/apt/sources.list.d/homebridge.list > /dev/null')
            self.hb_install_progress = 6
        
            os.system('sudo apt-get update')
            self.hb_install_progress = 20
        
            print("Starting Homebridge download")
        
            os.system('apt-get download homebridge')
            #p = subprocess.Popen(["apt-get","download","homebridge"], cwd=self.hb_path)
            #p.wait()
        
        
            # Check if homebridge deb file downloaded and get .deb file name, e.g. homebridge_1.0.34_arm64.deb
            deb_file_name = ""
            files = os.listdir(self.hb_path)
            print("files: " + str(files))
            for file_name in files:
                if os.path.isfile(file_name):
                    if file_name.startswith("homebridge") and file_name.endswith('.deb'):
                        print("Homebridge deb file downloaded succesfully")
                        deb_file_name = file_name
                        self.hb_install_progress = 40
                        break
        
            # ALT using shell
            deb_file = shell("ls " + str(self.hb_path)).rstrip()
            print("deb_file: " + str(deb_file))
            
            if deb_file_name == "":
                print("Error, Homebridge deb file failed to download")
                self.hb_install_progress = -40
                self.busy_intalling_hb = False
                return
        
            print("Extracting tar files")
            os.system("ar x " + str(deb_file_name))
        
            os.system("rm " + str(deb_file_name))
        
            os.system("tar xf control.tar.xz")
            os.system("rm control.tar.xz")
            self.hb_install_progress = 60
            print("control.tar.xz done")
        
            os.system("tar xf data.tar.xz")
            os.system("rm data.tar.xz")
            self.hb_install_progress = 80
            print("data.tar.xz done")

            # Check if homebridge is fully installed
            if os.path.isfile(self.hb_service_path):
                print("Homebridge installed succesfully")

                print("Installing homebridge-webthings Node module")
                p = subprocess.Popen([self.adapter.hb_npm_path,"install","--save","git+https://github.com/createcandle/homebridge-webthings.git"], cwd=self.adapter.hb_plugins_path)
                p.wait()
        
                self.adapter.update_installed_plugins_list()
                
                self.hb_installed = True
                self.hb_install_progress = 100
                
                # now start Homebridge
                self.run_hb()
                
            else:
                print("Homebridge failed to fully install")
                self.hb_install_progress = -100
            
        except Exception as ex:
            print("Error in intall_hb: " + str(ex))
        

        self.busy_intalling_hb = False







    def run_hb(self):
        print("IN RUN_HB")
        os.system('pkill hb-service')
        time.sleep(1)
        
        # Update the config file
        if not os.path.isfile(self.hb_config_file_path):
            print("Error, Homebridge configuration file does not exist")
            self.hb_installed = False
            return
        
        made_modifications = False
        
        try:
            with open(self.hb_config_file_path) as f:
                self.hb_config_data = json.load(f)
                if self.DEBUG:
                    print('Homebridge config was loaded from file: ' + str(self.hb_config_file_path))
                    print("self.hb_config_data: " + str(self.hb_config_data))
                    
                if not "bridge" in self.hb_config_data:
                    if self.DEBUG:
                        print('ERROR, config data did not have bridge object. Aborting launch.')
                    return
                
                self.setup_id = self.hb_config_data["bridge"]["name"][-4:]
                if self.DEBUG:
                    print("SETUP ID: " + str(self.setup_id))
                
                # name
                #if self.hb_name != "Candle Homebridge":
                #    self.hb_config_data["bridge"]["name"] = self.hb_name
                #el
                if not "Candle" in self.hb_config_data["bridge"]["name"]:
                    self.hb_config_data["bridge"]["name"] = "Candle " + str(self.hb_config_data["bridge"]["name"])
                    made_modifications = True
                    
                    
                """
                   {
                       "accessory": "webthings",
                       "confirmationIndicateOffline": true,
                       "manufacturer": "Candle",
                       "name": "Candle carbon sensor",
                       "password": "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImQwZDUwMTIwLTM2MjctNDBkNy1hMGI3LWI2ZjYxZDFhZmIxNSJ9.eyJjbGllbnRfaWQiOiJsb2NhbC10b2tlbiIsInJvbGUiOiJhY2Nlc3NfdG9rZW4iLCJzY29wZSI6Ii90aGluZ3M6cmVhZHdyaXRlIiwiaWF0IjoxNjg4OTgyNDc0LCJpc3MiOiJOb3Qgc2V0LiJ9.n5EQYmCYSuNLOFisSA_PtF-aUXglvUxfsbB9LYlZBsqi2u7a8T0rxRJh7KwsC7XlHyH7O2qF7DT0aC2jqkBdig",
                       "topics": {
                           "getCarbonDioxideLevel": "z2m-0xa4c138b4793c8e79/co2"
                       },
                       "type": "carbonDioxideSensor",
                       "username": "nousername"
                   }
                    
                """
                    
                try:
                    old_webthings_accessory_indexes = []
                    for index,accessory in enumerate(self.hb_config_data["accessories"]):
                        if self.DEBUG:
                            print("run_hb: accessory #" + str(index))
                            #print(json.dumps(accessory, indent=4, sort_keys=True))
                        if accessory['accessory'] == 'webthings':
                            #print("adding old index to remove later: " + str(index))
                            old_webthings_accessory_indexes.append(index)
                    
                    # Remove config (sort them from high to low to make the array popping work without issue)
                    old_webthings_accessory_indexes.sort(reverse=True)
                    if self.DEBUG:
                        print("sorted old_webthings_accessory_indexes: " + str(old_webthings_accessory_indexes))
                    for old_ac_index in old_webthings_accessory_indexes:
                        #print("old_ac_index: " + str(old_ac_index))
                        self.hb_config_data["accessories"].pop(old_ac_index)
                        
                    #print("cleaned up self.hb_config_data: " + str(self.hb_config_data))
                    
                    
                    # Recreate config
                    for ac in self.persistent_data['things']:
                        #print("ac: ")
                        #print(json.dumps(ac, indent=4))
                        
                        new_ac = {
                                "name": ac['thing_title'],
                                "type": ac['accessory_data']['homekit_type'],
                                "manufacturer": "Candle",
                                "accessory": "webthings",
                                "topics": {},
                                "username": "",
                                "password": self.persistent_data['token']
                                }
                        
                        for service in ac['accessory_data']['services']:
                            #print("service: " + str(service))
                            new_ac['topics'][ service['config_name'] ] = service['thing_id'] + "/" + service['property_id']
                                
                        for extra in ac['accessory_data']['extras']:
                            print("TODO: extra: " + str(extra))
                            for k, v in extra.items():
                                if self.DEBUG:
                                    print("setting extra: " + str(k) + " -> " + str(v))
                                new_ac[k] = v
                        
                        #print("new_ac: " + str(new_ac))
                        self.hb_config_data["accessories"].append(new_ac)
                        made_modifications = True
                    
                    if self.DEBUG:
                        print("UPDATED HOMEBRIDGE CONFIG DATA:")
                        print(json.dumps(self.hb_config_data, indent=4))
                        
                    
                        #thing_still_shared = False
                        #for ac in self.persistent_data['things']:
                        #    if self.DEBUG:
                        #        print("run_hb: AC to modify or add: " + str(ac))
                                #print( str(self.persistent_data['things'][thing] ))
                
                except Exception as ex:
                    if self.DEBUG:
                        print("Error modifying config file: " + str(ex))
                    
            if made_modifications is True:
                if self.DEBUG:
                    print("Saving modified config file")
                try:
                   json.dump( self.hb_config_data, open( self.hb_config_file_path, 'w+' ) )    
                except Exception as ex:
                    if self.DEBUG:
                        print("Error saving modified config file: " + str(ex) )
            
        except Exception as ex:
            if self.DEBUG:
                print("Error, could not load or parse config file: " + str(ex))
        
        
        if self.DEBUG:
            print("starting the homebridge thread")
        try:
            #self.really_run_hb()
            self.t = threading.Thread(target=self.really_run_hb)
            self.t.daemon = True
            self.t.start()
        except:
            if self.DEBUG:
                print("Error starting the homebridge thread")






    def really_run_hb(self):
        print("in run_hb")

        if not os.path.isfile(self.hb_service_path):
            print("Error, hb not installed properly?")
            return

        # exec /home/pi/.webthings/hb/opt/homebridge/bin/node /home/pi/.webthings/hb/opt/homebridge/lib/node_modules/homebridge-config-ui-x/dist/bin/hb-service.js run -I -U /home/pi/.webthings/hb/var/lib/homebridge -P /home/pi/.webthings/hb/var/lib/homebridge/node_modules --strict-plugin-resolution "$@"

        hb_command = ""
        hb_command += str(self.hb_node_path)  # could potentially skip this if the node versions are equal
        hb_command += " " + str(self.hb_service_path)
        hb_command += " run -I -U " + str(self.hb_storage_path) + " -P " + str(self.hb_plugins_path)
        #hb_command += " --strict-plugin-resolution" #--stdout
        
        self.launched = True

        while self.running:
            if self.DEBUG:
                print("__")
                print("HOMEBRIDGE COMMAND")
                print(str( hb_command ))
            
            self.hb_process = subprocess.Popen(hb_command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                                 #stderr=subprocess.PIPE, universal_newlines=True, preexec_fn=os.setpgrp)
            
            self.hb_process_pid = self.hb_process.pid
            if self.DEBUG:
                print("hb process PID = " + str(self.hb_process_pid))
            
            
            
            while self.running:
                
                # Read both stdout and stderr simultaneously
                sel = selectors.DefaultSelector()
                sel.register(self.hb_process.stdout, selectors.EVENT_READ)
                sel.register(self.hb_process.stderr, selectors.EVENT_READ)
                
                for key, val1 in sel.select():
                    line = key.fileobj.readline()
                    print("???" + str(line))
                    if not line:
                        #pass
                        #break
                        continue
                    if key.fileobj is self.hb_process.stdout:
                        #if self.DEBUG:
                        #print(f"STDOUT: {line}", end="", file=sys.stdout)
                        self.parse_hb(f"{line}")
                    else:
                        #print(f"STDERR: {line}", end="", file=sys.stderr)
                        self.parse_hb(f"{line}")
                time.sleep(0.1)
            
                    
        if self.DEBUG:
            print("BEYOND HOMEBRIDGE LOOP")



    # not used anymore in favour of reading the log file instead
    def parse_hb(self,line):
        if self.DEBUG:
            print("parse_hb got line: " + str(line))
        if line.startswith('X-HM:'):
            self.qr_code_url = str(line).rstrip()
            if self.DEBUG:
                print("spotted QR code url: " + str(self.qr_code_url))


        
    def update_installed_plugins_list(self):
        print("in update_installed_plugins_list")
        self.plugins_list = []
        files = os.listdir(self.hb_plugins_path)
        if self.DEBUG:
            print("plugin directories in node_modules: " + str(files))
        for file_name in files:
            print(str(file_name))
            file_path = os.path.join(self.hb_plugins_path,file_name)
            if os.path.isdir(file_path):
                if self.DEBUG:
                    print("is dir: " + str(file_path))
                if file_name.startswith(".") or file_name == 'homebridge':
                    if self.DEBUG:
                        print("spotted hidden or homebridge node module, should ignore this")
                    continue
                    
                #dir_size = os.path.getsize(file_path)
                #if self.DEBUG:
                #    print("dir_size:",dir_size)
                    
                #if file_name.startswith("homebridge") and file_name.endswith('.deb'):
                self.plugins_list.append({'name':file_name,'value':1})

        print("self.plugins_list: " + str(self.plugins_list))



    #
    #  CHANGING THE PROPERTIES
    #

    # It's nice to have a central location where a change in a property is managed.

    def set_state(self,state):
        try:
            print("in set_state with state: " + str(state))
        
            # saves the new state in the persistent data file, so that the addon can restore the correct state if it restarts
            self.persistent_data['state'] = state
            self.save_persistent_data() 
        
            # A cool feature: you can create popups in the interface this way:
            if state == True:
                self.send_pairing_prompt("You switched on the thing") # please don't overdo it with the pairing prompts..
        
            # We tell the property to change its value. This is a very round-about way, and you could place all this logic inside the property instead. It's a matter of taste.
            try:
                self.devices['homebridge-thing'].properties['state'].update( state )
            except Exception as ex:
                print("error setting state on thing: " + str(ex))
        
        except Exception as ex:
            print("error in set_state: " + str(ex))
                
        
        
        
    def set_slider(self,value):
        try:
            print("in set_slider with value: " + str(value))
        
            # saves the new state in the persistent data file, so that the addon can restore the correct state if it restarts
            self.persistent_data['slider'] = value
            self.save_persistent_data() 
        
            try:
                self.devices['homebridge-thing'].properties['slider'].update( value )
            except Exception as ex:
                print("error setting slider value on thing: " + str(ex))
            
        except Exception as ex:
            print("error in set_slider: " + str(ex))
        
        
        
    def set_dropdown(self,value):
        try:
            print("in set_dropdown with value: " + str(value))
        
            # saves the new state in the persistent data file, so that the addon can restore the correct state if it restarts
            self.persistent_data['dropdown'] = value
            self.save_persistent_data() 
        
            # A cool feature: you can create popups in the interface this way:
            self.send_pairing_prompt("new dropdown value: " + str(value))
        
            try:
                self.devices['homebridge-thing'].properties['dropdown'].update( value )
            except Exception as ex:
                print("error setting dropdown value on thing: " + str(ex))
        
        except Exception as ex:
            print("error in set_dropdown: " + str(ex))




    #
    # The methods below are called by the controller
    #

    def start_pairing(self, timeout):
        """
        Start the pairing process. This starts when the user presses the + button on the things page.
        
        timeout -- Timeout in seconds at which to quit pairing
        """
        print("in start_pairing. Timeout: " + str(timeout))
        
        
    def cancel_pairing(self):
        """ Happens when the user cancels the pairing process."""
        # This happens when the user cancels the pairing process, or if it times out.
        print("in cancel_pairing")
        

    def unload(self):
        """ Happens when the user addon / system is shut down."""
        if self.DEBUG:
            print("Bye!")
            
        self.running = False
            
        try:
            self.devices['homebridge-thing'].properties['status'].update( "Bye")
        except Exception as ex:
            print("Error setting status on thing: " + str(ex))
        
        # Tell the controller to show the device as disconnected. This isn't really necessary, as the controller will do this automatically.
        self.devices['homebridge-thing'].connected_notify(False)
        
        # A final chance to save the data.
        self.save_persistent_data()


        shell("sudo kill {}".format(self.hb_process_pid))
        time.sleep(1)
        os.system('pkill hb-service')


    def remove_thing(self, device_id):
        """ Happens when the user deletes the thing."""
        print("user deleted the thing")
        try:
            # We don't have to delete the thing in the addon, but we can.
            obj = self.get_device(device_id)
            self.handle_device_removed(obj) # Remove from device dictionary
            if self.DEBUG:
                print("User removed thing")
        except:
            print("Could not remove thing from devices")




    #
    # This saves the persistent_data dictionary to a file
    #
    
    def save_persistent_data(self):
        if self.DEBUG:
            print("Saving to persistence data store")

        try:
            if not os.path.isfile(self.persistence_file_path):
                open(self.persistence_file_path, 'a').close()
                if self.DEBUG:
                    print("Created an empty persistence file")
            else:
                if self.DEBUG:
                    print("Persistence file existed. Will try to save to it.")

            with open(self.persistence_file_path) as f:
                if self.DEBUG:
                    print("saving: " + str(self.persistent_data))
                try:
                    json.dump( self.persistent_data, open( self.persistence_file_path, 'w+' ) )
                except Exception as ex:
                    print("Error saving to persistence file: " + str(ex))
                return True
            #self.previous_persistent_data = self.persistent_data.copy()

        except Exception as ex:
            if self.DEBUG:
                print("Error: could not store data in persistent store: " + str(ex) )
        
        return False







#
# DEVICE
#

# This addon is very basic, in that it only creates a single thing.
# The device can be seen as a "child" of the adapter

# Adapter
# - Device  <- you are here
# - - Property  
# - Api handler


class HomebridgeDevice(Device):
    """Internet Radio device type."""

    def __init__(self, adapter):
        """
        Initialize the object.
        adapter -- the Adapter managing this device
        """

        Device.__init__(self, adapter, 'homebridge')

        self._id = 'homebridge-thing' # TODO: probably only need the first of these
        self.id = 'homebridge-thing'
        self.adapter = adapter
        self.DEBUG = adapter.DEBUG

        self.name = 'thing1' # TODO: is this still used? hasn't this been replaced by title?
        self.title = 'Homebridge thing'
        self.description = 'The Homebridge thing'
        
        # We give this device an optional "capability". This will cause it to have a nicer icon that indicates what it can do. 
        # Capabilities are always a combination of giving a this a capability type, and giving at least one of its properties a capability type.
        # For example, here the device is a "multi level switch", which means it should have a boolean toggle property as well as a numeric value property
        # There are a lot of capabilities, read about them here: https://webthings.io/schemas/
        
        self._type = ['MultiLevelSwitch'] # a combination of a toggle switch and a numeric value

        try:
            
            # Let's add four properties:
            
            # This create a toggle switch property
            self.properties["state"] = HomebridgeProperty(
                            self,
                            "state",
                            {
                                '@type': 'OnOffProperty', # by giving the property this "capability", it will create a special icon indicating what it can do. Note that it's a string (while on the device it's an array).
                                'title': "State example",
                                'readOnly': False,
                                'type': 'boolean'
                            },
                            self.adapter.persistent_data['state']) # we give the new property the value that was remembered in the persistent data store
                            
                            
            # Creates a percentage slider
            self.properties["slider"] = HomebridgeProperty( # (here "slider" is just a random name)
                            self,
                            "slider",
                            {
                                '@type': 'LevelProperty', # by giving the property this "capability", it will create a special icon indicating what it can do.
                                'title': "Slider example",
                                'type': 'integer',
                                'readOnly': False,
                                'minimum': 0,
                                'maximum': 100,
                                'unit': 'percent'
                            },
                            self.adapter.persistent_data['slider'])
                        
                        
            # This property shows a simple string in the interface. The user cannot change this string in the UI, it's "read-only" 
            self.properties["status"] = HomebridgeProperty(
                            self,
                            "status",
                            {
                                'title': "Status",
                                'type': 'string',
                                'readOnly': True
                            },
                            "Hello world")


            self.properties["dropdown"] = HomebridgeProperty(
                            self,
                            "dropdown",
                            {
                                'title': "Dropdown example",
                                'type': 'string',
                                'readOnly': False,
                                'enum': ['Auto', 'Option 1', 'Option 2'],
                            },
                            self.adapter.persistent_data['dropdown']) 



        except Exception as ex:
            if self.DEBUG:
                print("error adding properties to thing: " + str(ex))

        if self.DEBUG:
            print("thing has been created.")


#
# PROPERTY
#
# The property can be seen as a "child" of a device

# Adapter
# - Device
# - - Property  <- you are here
# - Api handler

class HomebridgeProperty(Property):

    def __init__(self, device, name, description, value):
        # This creates the initial property
        
        # properties have:
        # - a unique id
        # - a human-readable title
        # value. The current value of this property
        
        Property.__init__(self, device, name, description)
        
        self.device = device # a way to easily access the parent device, of which this property is a child.
        
        # you could go up a few levels to get values from the adapter:
        # print("debugging? " + str( self.device.adapter.DEBUG ))
        
        # TODO: set the ID properly?
        self.id = name
        self.name = name # TODO: is name still used?
        self.title = name # TODO: the title isn't really being set?
        self.description = description # a dictionary that holds the details about the property type
        self.value = value # the value of the property
        
        # Notifies the controller that this property has a (initial) value
        self.set_cached_value(value)
        self.device.notify_property_changed(self)
        
        print("property: initiated: " + str(self.title) + ", with value: " + str(value))


    def set_value(self, value):
        # This gets called by the controller whenever the user changes the value inside the interface. For example if they press a button, or use a slider.
        print("property: set_value called for " + str(self.title))
        print("property: set value to: " + str(value))
        
        try:
            
            # Depending on which property this is, you could have it do something. That method could be anywhere, but in general it's clean to keep the methods at a higher level (the adapter)
            # This means that in this example the route the data takes is as follows: 
            # 1. User changes the property in the interface
            # 2. Controller calls set_value on property
            # 3. In this example the property routes the intended value to a method on the adapter (e.g. set_state). See below.
            # 4. The method on the adapter then does whatever it needs to do, and finally tells the property's update method so that the new value is updated, and the controller is sent a return message that the value has indeed been changed.
            
            #  If you wanted to you could simplify this by calling update directly. E.g.:
            # self.update(value)
            
            if self.id == 'state':
                self.device.adapter.set_state(bool(value))
        
            elif self.id == 'slider':
                self.device.adapter.set_slider(int(value))
        
            elif self.id == 'dropdown':
                self.device.adapter.set_dropdown(str(value))
        
            # The controller is waiting 60 seconds for a response from the addon that the new value is indeed set. If "notify_property_changed" isn't used before then, the controller will revert the value in the interface back to what it was.
            
        
        except Exception as ex:
            print("property: set_value error: " + str(ex))


    def update(self, value):
        # This is a quick way to set the value of this property. It checks that the value is indeed new, and then notifies the controller that the value was changed.
        
        print("property: update. value: " + str(value))
         
        if value != self.value:
            self.value = value
            self.set_cached_value(value)
            self.device.notify_property_changed(self)






#
#  API HANDLER
#

# In this example the api-handler is created by the adapter. This is arbitary, you could have the adapter be the child of the api-handler if you prefered.

# Adapter  
# - Device  
# - - Property  
# - Api handler  <- you are here



class HomebridgeAPIHandler(APIHandler):
    """API handler."""

    def __init__(self, adapter, verbose=False):
        """Initialize the object."""
        print("INSIDE API HANDLER INIT")
        
        self.adapter = adapter
        self.DEBUG = self.adapter.DEBUG


        # Intiate extension addon API handler
        try:
            
            APIHandler.__init__(self, self.adapter.addon_name) # gives the api handler the same id as the adapter
            self.manager_proxy.add_api_handler(self) # tell the controller that the api handler now exists
            
        except Exception as e:
            print("Error: failed to init API handler: " + str(e))
        
        
    #
    #  HANDLE REQUEST
    #

    def handle_request(self, request):
        """
        Handle a new API request for this handler.

        request -- APIRequest object
        """
        
        try:
        
            if request.method != 'POST':
                return APIResponse(status=404) # we only accept POST requests
            
            if request.path == '/ajax': # you could have all kinds of paths. In this example we only use this one, and use the 'action' variable to denote what we want to api handler to do

                try:
                    action = str(request.body['action']) 
                    
                    if self.DEBUG:
                        print("API handler is being called. Action: " + str(action))
                        print("request.body: " + str(request.body))
                    
                        
                    # INIT
                    if action == 'init':
                        if self.DEBUG:
                            print("API: in init")
                            
                        try:
                            # Get safe values from the config file
                            hb_name = "Candle Homebridge"
                            if "bridge" in self.adapter.hb_config_data:
                                hb_name = self.adapter.hb_config_data["bridge"]["name"]
                            else:
                                if self.DEBUG:
                                    print('ERROR, config data did not have bridge object (yet).')
                        except Exception as ex:
                            if self.DEBUG:
                                print("Error getting name: " + str(ex))
                                
                        return APIResponse(
                          status=200,
                          content_type='application/json',
                          content=json.dumps({
                                      'a_number_setting':self.adapter.a_number_setting,
                                      'thing_state':self.adapter.persistent_data['state'],
                                      'slider_value':self.adapter.persistent_data['slider'],
                                      'plugins_list':self.adapter.plugins_list,
                                      'hb_installed':self.adapter.hb_installed,
                                      'hb_install_progress':self.adapter.hb_install_progress,
                                      'launched':self.adapter.launched,
                                      'config_port':self.adapter.config_port,
                                      'hb_name':hb_name,
                                      'config_ip':self.adapter.ip,
                                      'hostname':self.adapter.hostname,
                                      'things':self.adapter.persistent_data['things'],
                                      'debug':self.adapter.DEBUG
                                      }),
                        )
                
                    
                    
                    elif action == 'save_token':
                        if self.DEBUG:
                            print("API: in save_token")
                        
                        state = False
                        
                        try:
                            self.adapter.persistent_data['token'] = str(request.body['token'])
                            self.adapter.save_persistent_data()
                            if self.DEBUG:
                                print("saved token")
                            state = True
                            
                        except Exception as ex:
                            if self.DEBUG:
                                print("Error saving token: " + str(ex))
                        
                        return APIResponse(
                          status=200,
                          content_type='application/json',
                          content=json.dumps({'state' : state}),
                        )
                    
                    
                    
                    elif action == 'save_things':
                        if self.DEBUG:
                            print("API: in save_things")
                        
                        state = False
                        
                        try:
                            self.adapter.persistent_data['things'] = request.body['things']
                            self.adapter.save_persistent_data()
                            if self.DEBUG:
                                print("saved new things list")
                            state = True
                            
                            # restart Homebridge # TODO: make this less rough..
                            os.system('pkill homebridge')
                            
                            
                        except Exception as ex:
                            if self.DEBUG:
                                print("Error saving things: " + str(ex))
                        
                        return APIResponse(
                          status=200,
                          content_type='application/json',
                          content=json.dumps({'state' : state}),
                        )
                    
                    
                    
                    # GET_PIN
                    # We should avoid sending this over the network too often, hence this special action
                    elif action == 'pair':
                        if self.DEBUG:
                            print("API: in pair")
                        state = False
                        
                        pin = ""
                        code = ""
                        try:
                            if "bridge" in self.adapter.hb_config_data and len(self.adapter.setup_id) > 0:
                                
                                pin = self.adapter.hb_config_data["bridge"]["pin"]
                                
                                if self.adapter.qr_code_url == "":
                                    with open(self.adapter.hb_logs_file_path) as f: 
                                        hb_log = f.read().splitlines()
                                        for line in hb_log:
                                            print("hb_log line: " + str(line))
                                            if line.startswith('X-HM:'):
                                                self.adapter.qr_code_url = str(line).rstrip()
                                                if self.DEBUG:
                                                    print("spotted QR code url: " + str(self.adapter.qr_code_url))
                                code = self.adapter.qr_code_url #generate_homekit_qr_code(2,pin,self.adapter.setup_id)
                                
                                if code != "":
                                    state = True
                                
                        except Exception as ex:
                            if self.DEBUG:
                                print("Error getting pin: " + str(ex))

                        return APIResponse(
                          status=200,
                          content_type='application/json',
                          content=json.dumps({'state':state,'code':code,'pin':pin}),
                        )
                    
                    
                    # INSTALL PLUGIN
                    elif action == 'install_plugin':
                        if self.DEBUG:
                            print("API: in install_plugin")
                        
                        state = False
                        
                        try:
                            name = str(request.body['name'])
                            version = str(request.body['version'])
                            
                            state = self.install_plugin(name,version) # This method returns True all the time..
                            
                        except Exception as ex:
                            if self.DEBUG:
                                print("Error installing plugin: " + str(ex))
                        
                        return APIResponse(
                          status=200,
                          content_type='application/json',
                          content=json.dumps({'state' : state}),
                        )
                    
                    
                    
                    # DELETE PLUGIN
                    elif action == 'delete_plugin':
                        if self.DEBUG:
                            print("API: in delete_plugin")
                        
                        state = False
                        
                        try:
                            name = str(request.body['name'])
                            
                            state = self.delete_plugin(name) # This method returns True if deletion was succesful
                            
                        except Exception as ex:
                            if self.DEBUG:
                                print("Error deleting: " + str(ex))
                        
                        return APIResponse(
                          status=200,
                          content_type='application/json',
                          content=json.dumps({'state' : state}),
                        )
                    
                    
                    else:
                        print("Error, that action is not possible")
                        return APIResponse(
                            status=404
                        )
                        
                except Exception as ex:
                    if self.DEBUG:
                        print("Ajax error: " + str(ex))
                    return APIResponse(
                        status=500,
                        content_type='application/json',
                        content=json.dumps({"error":"Error in API handler"}),
                    )
                    
            else:
                if self.DEBUG:
                    print("invalid path: " + str(request.path))
                return APIResponse(status=404)
                
        except Exception as e:
            if self.DEBUG:
                print("Failed to handle UX extension API request: " + str(e))
            return APIResponse(
                status=500,
                content_type='application/json',
                content=json.dumps({"error":"General API error"}),
            )
        

        # That's a lot of "apiResponse", but we need to make sure that there is always a response sent to the UI


    
    # Install a new plugin
    def install_plugin(self,name,version="@latest"):
        plugin_name_full = str(name) + str(version)
        if self.DEBUG:
            print("in install_plugin. Name: " + str(name) + " -> " + str(plugin_name_full))
        
        p = subprocess.Popen([self.adapter.hb_npm_path,"install","--save",plugin_name_full], cwd=self.adapter.hb_plugins_path)
        p.wait()
        
        self.adapter.update_installed_plugins_list()
        
        if self.DEBUG:
            print("plugin should now be installed")
        
        # Check if a directory with the plugin name now exists
        return os.path.isdir( os.path.join(self.adapter.hb_plugins_path,name) )
        #return True
    


    
    # Loop over all the items in the list, which is stored inside the adapter instance.
    def delete_plugin(self,name):
        print("in delete_plugin. Name: " + str(name))
        
        # uninstall via npm here
        p = subprocess.Popen([self.adapter.hb_npm_path,"uninstall",name], cwd=self.adapter.hb_plugins_path)
        p.wait()
        
        for i in range(len(self.adapter.plugins_list)):
            if self.adapter.plugins_list[i]['name'] == name:
                # Found it
                del self.adapter.plugins_list[i]
                print("deleted plugin from list")
                return True
                
        self.adapter.update_installed_plugins_list()
        
        # If we end up there, the name wasn't found in the list
        return True




def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except:
        IP = None
    finally:
        s.close()
    return IP


# From https://github.com/spmartin/homekit-qr-code-generator (MIT License)
def generate_homekit_qr_code(category, password, setup_id, version=0, reserved=0, flags=2):
    
        base36 = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        payload = 0
        payload |= (version & 0x7)

        payload <<= 4
        payload |= (reserved & 0xf)

        payload <<= 8
        payload |= (category & 0xff)

        payload <<= 4
        payload |= (flags & 0xf)

        payload <<= 27
        payload |= (int(password.replace('-', '')) & 0x7fffffff)

        encoded_payload = ''
        for _ in range(9):
            encoded_payload += base36[payload % 36]
            payload //= 36

        return 'X-HM://%s%s' % (''.join(reversed(encoded_payload)), setup_id)
    


def shell(command):
    #print("HOTSPOT SHELL COMMAND = " + str(command))
    shell_check = ""
    try:
        shell_check = subprocess.check_output(command, shell=True)
        shell_check = shell_check.decode("utf-8")
        shell_check = shell_check.strip()
    except:
        pass
    return shell_check 
        


def kill(command):
    check = ""
    try:
        search_command = "ps ax | grep \"" + command + "\" | grep -v grep"
        #print("hotspot: in kill, search_command = " + str(search_command))
        check = shell(search_command)
        #print("hotspot: check: " + str(check))

        if check != "":
            #print("hotspot: Process was already running. Cleaning it up.")

            old_pid = check.split(" ")[0]
            #print("- hotspot: old PID: " + str(old_pid))
            if old_pid != None:
                os.system("sudo kill " + old_pid)
                #print("- hotspot: old process has been asked to stop")
                time.sleep(1)
        
    except Exception as ex:
        pass