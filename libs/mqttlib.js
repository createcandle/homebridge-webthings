// MQTT Thing Accessory plugin for Homebridge
// MQTT Library
// Modified by Candle to connect to Webthings instead of MQTT

'use strict'; // eslint-disable-line

//const mqtt = require( "mqtt" );
const path = require( "path" );
const fs = require( "fs" );
const jsonpath = require( "jsonpath" );

//import {WebThingsClient} from 'webthing-client';
//const { WebThingsClient } = require('../lib/webthings-client');
const { WebThingsClient } = require('webthings-client');
//const WebThingsClient = require( "webthings-client" );




var mqttlib = new function() {

    /*
    function logit( message ){
        fs.appendFile('/home/pi/.webthings/data/homebridge/modlog.txt', message, function (err) {
            if (err) throw err;
            //console.log('Saved!');
        });
    }
    */

    function makeCodecPath( codec, homebridgePath ) {
        logit("makeCodecPath: codec: " + codec);
        let codecPath = codec;
        // if it doesn't start with a '/' (i.e. not fully-qualified)...
        if( codecPath[ 0 ] != '/' ) {
            if( codecPath.substr( codecPath.length - 3 ) !== '.js' ) {
                // no js extension - assume it's an internal codec
                codecPath = path.join( __dirname, '../codecs/', codecPath + '.js' );
            } else {
                // relative external codec is relative to homebridge userdata
                codecPath = path.join( homebridgePath, codecPath );
            }
        }
        return codecPath;
    }

    function optimizedPublish( topic, message, ctx ) {
        console.log("optimizedPublish: topic: ", topic, message);
        //const { config, log, mqttClient } = ctx;
        const { config, log } = ctx;
        //console.log("optimizedPublish: config: " + config.to_string() );
        //console.log("optimizedPublish: log: " + log.to_string() );
        const messageString = message.toString();
        console.log("optimizedPublish: messageString: " + messageString );
        if( config.optimizePublishing && ctx.lastPubValues ) {
            if( ctx.lastPubValues[ topic ] == messageString ) {
                console.warn("optimizedPublish: not republishing same value");
                // optimized - don't publish
                return;
            }
            // store what we're about to publish
            ctx.lastPubValues[ topic ] = messageString;
        }
        if( config.logMqtt ) {
            log( 'Publishing MQTT: ' + topic + ' = ' + messageString );
        }
        //console.log("optimizedPublish: publishing with: topic, messageString, config.mqttPubOptions: "), topic, messageString, config.mqttPubOptions;
        //mqttClient.publish( topic, messageString, config.mqttPubOptions );
        
        if(typeof ctx.webthingsClient == 'undefined'){
            //console.log("warning, webthings client was not in context (yet)");
        }
        else{
            //console.log("hurray, webthings client exists in context");
            if(typeof ctx.config.topics != 'undefined'){
                //console.log("publish topics exists: ", ctx.config.topics);
                
                if(typeof ctx.device != 'undefined'){
                    //console.log("DEVICE ALREADY IN CTX");
                    
                    try {
                        
                        let property_id = topic.substring(topic.indexOf("/") + 1,topic.length);
                        console.log('property_id: ', property_id);
                        //console.log("ctx.device.properties: ", ctx.device.properties);
                        
                        const property = ctx.device.properties[property_id];
                        if(typeof property.description != 'undefined'){
                            console.log("property.description: ", property.description);
                            if (!property.description.readOnly){
                                
                                const property_url = "/properties/" + property.description.name;
                                const full_url = '/things/' + ctx.device_id + property_url;
                                //console.log("SENDING: ", full_url, message);
                                /*
                                if(typeof property.description.links == 'undefined'){
                                    console.log("adding links/href to property description, oldschool");
                                    property.description.links = [{"href":property_url,"rel":"property"}];
                                };
                                */
                                //const wrapper = {[this.name]: value};
                                
                                const setProp = async function () { 
                                    let myPromise = new Promise(function(myResolve, myReject) {
                                        //await ctx.device.client.put(property_url, message);
                                        try{
                                            //property.setValue(message) // causes "property has no links" (not using forms yet)
                                            ctx.device.client.put(full_url, message)
                                            .then(() => {
                                                //console.log('client success');
                                            }).catch((e) => {
                                                //console.log('client put error: ', e);
                                                myReject("crash");
                                            });
                                            myResolve(true);
                                        } 
                                        catch (e){
                                            console.log("rejected");
                                            myReject("crash");
                                        }
                                    });
                                    return myPromise;
                                }

                                setProp()
                                .then(() => { console.log("setProp done") })
                                .catch(e => {
                                    console.log("setProp error",e);
                                });
                                
                                
                                
                            }
                            else{
                                console.warn("warning, property is readOnly, ignoring");
                            }
                        }
                        else{
                            console.error("error, property had no description");
                        }
                        
                    } catch (err) {
                        console.error("yikes, error in publish: ", err);
                    }
                    
                }
                else{
                    console.error("ERROR, device not yet in CTX");
                }
                
            }
            else{
                console.error("ctx.config.topics was undefined");
            }
        }
        
    }

    //! Initialise MQTT. Requires context ( { log, config } ).
    //! Context populated with mqttClient and mqttDispatch, and if publishing optimization is enabled lastPubValues.
    this.init = function( ctx ) {
        console.log("in this.init");
        console.log("ctx: ", ctx);
        // MQTT message dispatch
        let mqttDispatch = ctx.mqttDispatch = {}; // map of topic to [ function( topic, message ) ] to handle
        let propDispatch = ctx.propDispatch = {}; // map of property to [ rawhandler( topic, message ) ]

        let { config, log } = ctx;

        // create cache of last-published values for publishing optimization
        if( config.optimizePublishing ) {
            ctx.lastPubValues = {};
        }

        let logmqtt = config.logMqtt;
        var clientId = 'mqttthing_' + config.name.replace(/[^\x20-\x7F]/g, "") + '_' + Math.random().toString(16).substr(2, 8);

        // Load any codec
        if( config.codec ) {
            let codecPath = makeCodecPath( config.codec, ctx.homebridgePath );
            if( fs.existsSync( codecPath ) ) {
                // load codec
                //console.log( 'Loading codec from ' + codecPath );
                let codecMod = require( codecPath );
                if( typeof codecMod.init === "function" ) {

                    // direct publishing
                    let directPub = function( topic, message ) {
                        optimizedPublish( topic, message, ctx );
                    };

                    // notification by property
                    let notifyByProp = function( property, message ) {
                        let handlers = propDispatch[ property ];
                        if( handlers ) {
                            for( let i = 0; i < handlers.length; i++ ) {
                                handlers[ i ]( '_prop-' + property, message );
                            }
                        }
                    };

                    // initialise codec
                    let codec = ctx.codec = codecMod.init( { log, config, publish: directPub, notify: notifyByProp } );
                    if( codec ) {
                        // encode/decode must be functions
                        if( typeof codec.encode !== "function" ) {
                            log.warn( 'No codec encode() function' );
                            codec.encode = null;
                        }
                        if( typeof codec.decode !== "function" ) {
                            log.warn( 'No codec decode() function' );
                            codec.decode = null;
                        }
                    }
                } else {
                    // no initialisation function
                    log.error( 'ERROR: No codec initialisation function returned from ' + codecPath );
                }
            } else {
                log.error( 'ERROR: Codec file [' + codecPath + '] does not exist' );
            }
        }

        // start with any configured options object
        var options = config.mqttOptions || {};

        // standard options set by mqtt-thing
        var myOptions = {
            keepalive: 10,
            clientId: clientId,
            protocolId: 'MQTT',
            protocolVersion: 4,
            clean: true,
            reconnectPeriod: 1000,
            connectTimeout: 30 * 1000,
            will: {
                topic: 'WillMsg',
                payload: 'mqtt-thing [' + ctx.config.name + '] has stopped',
                qos: 0,
                retain: false
            },
            username: config.username || process.env.MQTTTHING_USERNAME,
            password: config.password || process.env.MQTTTHING_PASSWORD,
            rejectUnauthorized: false
        };

        // copy standard options into options unless already set by user
        for( var opt in myOptions ) {
            if( myOptions.hasOwnProperty( opt ) && ! options.hasOwnProperty( opt ) ) {
                options[ opt ] = myOptions[ opt ];
            }
        }

        // load ca/cert/key files
        if( options.cafile ) {
            options.ca = fs.readFileSync( options.cafile );
        }
        if( options.certfile ) {
            options.cert = fs.readFileSync( options.certfile );
        }
        if( options.keyfile ) {
            options.key = fs.readFileSync( options.keyfile );
        }

        // insecure
        if( options.insecure ) {
            options.checkServerIdentity = function( /* servername, cert */ ) {
                return undefined; /* servername and certificate are verified */
            };
        }

        // add protocol to url string, if not yet available
        let brokerUrl = config.url || process.env.MQTTTHING_URL;
        if( brokerUrl && ! brokerUrl.includes( '://' ) ) {
            brokerUrl = 'mqtt://' + brokerUrl;
        }

        // log MQTT settings
        if( logmqtt ) {
            log( 'MQTT URL: ' + brokerUrl );
            log( 'MQTT options: ' + JSON.stringify( options, function( k, v ) {
                if( k == "password" ) {
                    return undefined; // filter out
                }
                return v;
            } ) );
        }

        var wt_client;
        //console.log("options.password: ", options.password)
        const token = options.password; //'eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImQwZDUwMTIwLTM2MjctNDBkNy1hMGI3LWI2ZjYxZDFhZmIxNSJ9.eyJjbGllbnRfaWQiOiJsb2NhbC10b2tlbiIsInJvbGUiOiJhY2Nlc3NfdG9rZW4iLCJzY29wZSI6Ii90aGluZ3M6cmVhZHdyaXRlIiwiaWF0IjoxNjg4OTgyNDc0LCJpc3MiOiJOb3Qgc2V0LiJ9.n5EQYmCYSuNLOFisSA_PtF-aUXglvUxfsbB9LYlZBsqi2u7a8T0rxRJh7KwsC7XlHyH7O2qF7DT0aC2jqkBdig';

        if(options.password.length == 0){
            console.log("password not long enough for ", ctx.config);
            return;
        }

        let myFunc = async function () { 
            let createWebthingsClient = new Promise(function(myResolve, myReject) {
            
                let webt_client = WebThingsClient.local(token);
                myResolve(webt_client);
                myReject("Error creating webthings client");
            });
            return await createWebthingsClient;
        }
        

        myFunc()
        .then(
            function(value) {
                //console.log("hurray webthings client initialised");
                wt_client = value;
                
                wt_client.on('error', (error) => {
                    console.log('Something went wrong', error);
                });
                wt_client.on('close', () => {
                    console.log('Connection closed');
                });
                wt_client.on('propertyChanged', (device_id, property_name, value) => {
                    //console.log(device_id, ':', `Property ${property_name} changed to ${value}`);
                    
                    
                    //console.log("Received Webthing: " + device_id + "/" + property_name + " with value: " + value);
                    let topic = device_id + "/" + property_name;
                    let handlers = mqttDispatch[topic];
                    if (handlers) {
                        //console.log("HANDLER FOUND:", handlers);
                        //console.log(device_id, ':', `Property ${property_name} changed to ${value} at topic: ${topic}`);
                        for( let i = 0; i < handlers.length; i++ ) {
                            //console.log("handler #: " + i);
                            handlers[ i ]( topic,value );
                        }
                    } else {
                        //log('Warning: No MQTT dispatch handler for topic [' + topic + ']');
                    }
                    
                    
                });
                wt_client.on('actionTriggered', (device_id, action_name, info) => {
                    //console.log(device_id, ':', `Action ${action_name} triggered with input ${JSON.stringify(info.input)}`);
                });
                wt_client.on('eventRaised', (device_id, event_name, info) => {
                    //console.log(device_id, ':', `Event ${event_name} raised: ${info.data}`);
                });
                wt_client.on('connectStateChanged', (device_id, state) => {
                    //console.log(device_id, ':', state ? 'connected' : 'disconnected');
                });
                wt_client.on('deviceModified', (device_id) => {
                    //console.log(device_id, ':', 'modified');
                });
                wt_client.on('deviceAdded', (device_id) => {
                    //log(device_id);
                    //console.log(device_id, ':', 'added');
                    
                    let get_device = new Promise(function(myResolve, myReject) {
                        let dev = wt_client.getDevice(device_id);
                        if(dev != null){
                            myResolve(dev);
                        }
                        else{
                            console.error("Error finding webthings device");
                            myReject("Error finding webthings device");
                        }
                    });
                    
                    get_device()
                    .then( (device) => { 
                        console.log("subscribing to device event");
                        wt_client.subscribeEvents(device, device.events);
                    });
                    
                    //const device = await webThingsClient.getDevice(device_id);
                    //await webThingsClient.subscribeEvents(device, device.events);
                    
                    //console.log(device.id(), ':', 'Subscribed to all events');
                });
                wt_client.on('deviceRemoved', (device_id) => {
                    //console.log(device_id, ':', 'removed');
                });
                wt_client.on('pair', (info) => {
                    //console.log('pair', info.status);
                });
                
                return wt_client;
                //myDisplayer(value);
            },
            function(error) {
                console.log("ug oh, error in wt: ", error);
            }
        )
        
        .then(
            function(value) {
                //console.log("hurray, will to to connect to webthings webclient");
                wt_client = value;
                
                ctx.webthingsClient = wt_client;
                
                //return wt_client.connect();
                wt_client.connect()
                .then( () => {
                    setTimeout(async () => {
                        //console.log("post wt connect: ctx.config: ", ctx.config);
                        const devices = await wt_client.getDevices();
                        //console.log("post wt connect: devices keys: ", Object.keys(devices));
                        var b = 0;
                        for (const device of devices) {
                            b++;
                            //console.log("*" + b);
                            //console.log("device type: ", typeof device.description );
                            //console.log("keys: ", Object.keys(device.description));
                            //console.log();
                            
                            try{
                                if(typeof ctx.config.topics != 'undefined'){
                                    //console.log("topics exists: ", ctx.config.topics);
                                    var first_key = Object.keys(ctx.config.topics)[0];
                                    first_key = ctx.config.topics[first_key];
                                    //console.log("first topic: ", first_key);
                                    //if(first_key.length > 2){
                                    if(first_key.indexOf("/") > -1){
                                        //console.log("topic has slash");
                                        first_key = first_key.substring(0, first_key.indexOf("/"));
                                        //console.log("first_key: ", first_key);
                                        //console.log("device.description.href: ", device.description.href);
                                        
                                        //if(device.description.href.endsWith('/' + first_key)){
                                        if(device.description.href == '/things/' + first_key){
                                            //console.log("subscribing to device events for: ", first_key);
                                            await wt_client.subscribeEvents(device, device.events);
                                            ctx.device_id = first_key;
                                            ctx.device = device;
                                        }
                                    }
                                }
                            }
                            catch(e){
                                console.error("wt: error looking for specific device to subscribe to: ", e);
                            }
                            
                            
                            
                            
                            
                            //webThingsClient.subscribeEvents(device, device.events);
                            //console.log(device.id(), ':', 'Subscribed to all events');
                            //log('Subscribed to all events');
                        }
                    }, 100);
                })
            }
        );


        /*
        var wt_client;
        //const wt_client = makeWebthingsClient(token);
        makeWebthingsClient(token)
        .then((obj) => {
            log("hurray then called");
            wt_client = obj;
            
            try {
                //await webThingsClient.connect();
                wt_client.connect()
                .then( () => {
                    setTimeout(async () => {
                        const devices = await wt_client.getDevices();
                        for (const device of devices) {
                            await wt_client.subscribeEvents(device, device.events);
                            //webThingsClient.subscribeEvents(device, device.events);
                            console.log(device.id(), ':', 'Subscribed to all events');
                        }
                    }, 100);
                })

            
            } catch(e) {
                console.warn(`Could not connect to gateway`);
            }
        })
        */
        //(async () => {
            
        //})();
        
        
        
        //const wt_client = async () => { await WebThingsClient.local(token) };
        //log(wt_client);
        
        



        // create MQTT client
        /*
        var mqttClient = mqtt.connect(brokerUrl, options);
        mqttClient.on('error', function (err) {
            log('MQTT Error: ' + err);
        });

        mqttClient.on('message', function (topic, message) {
            console.log("in mqttClient on message. topic, message: ", topic, message);
            if (logmqtt) {
                log("Received MQTT: " + topic + " = " + message);
            }
            let handlers = mqttDispatch[topic];
            if (handlers) {
                for( let i = 0; i < handlers.length; i++ ) {
                    handlers[ i ]( topic, message );
                }
            } else {
                log('Warning: No MQTT dispatch handler for topic [' + topic + ']');
            }
        });

        ctx.mqttClient = mqttClient;
        return mqttClient;
        */
    };

    function getApplyState( ctx, property ) {
        if( ! ctx.hasOwnProperty( 'applyState' ) ) {
            ctx.applyState = { props: {}, global: {} };
        }
        if( ! ctx.applyState.props.hasOwnProperty( property ) ) {
            ctx.applyState.props[ property ] = { global: ctx.applyState.global };
        }
        return ctx.applyState.props[ property ];
    }

    function getCodecFunction( codec, property, functionName ) {
        if( codec ) {
            let fn;
            if( codec.properties && codec.properties[ property ] ) {
                fn = codec.properties[ property ][ functionName ];
            }
            if( fn === undefined ) {
                fn = codec[ functionName ];
            }
            return fn;
        }
    }

    // Subscribe
    this.subscribe = function( ctx, topic, property, handler ) {
        console.log("mqttlib: in subscribe. topic: ", topic);
        let rawHandler = handler;
        //let { mqttDispatch, log, mqttClient, codec, propDispatch, config } = ctx;
        let { mqttDispatch, log, codec, propDispatch, config } = ctx;
        /*
        if( ! mqttClient ) {
            log( 'ERROR: Call mqttlib.init() before mqttlib.subscribe()' );
            return;
        }
        */

        // debounce
        if( config.debounceRecvms ) {
            //console.log("doing debounce. config.debounceRecvms: ", config.debounceRecvms);
            let origHandler = handler;
            let debounceTimeout = null;
            handler = function( intopic, message ) {
                if( debounceTimeout ) {
                    clearTimeout( debounceTimeout );
                }
                debounceTimeout = setTimeout( function() {
                    origHandler( intopic, message );
                }, config.debounceRecvms );
            };
        }

        let extendedTopic = null;
        // send through any apply function
        if (typeof topic != 'string') {
            //console.error("topic was not string somehow");
            extendedTopic = topic;
            topic = extendedTopic.topic;
            if (extendedTopic.hasOwnProperty('apply')) {
                let previous = handler;
                let applyFn = Function( "message", "state", extendedTopic['apply'] ); //eslint-disable-line
                handler = function (intopic, message) {
                    let decoded;
                    try {
                        decoded = applyFn( message, getApplyState( ctx, property ) );
                        if( config.logMqtt ) {
                            log( 'apply() function decoded message to [' + decoded + ']' );
                        }
                    } catch( ex ) {
                        log( 'Decode function apply( message) { ' + extendedTopic.apply + ' } failed for topic ' + topic + ' with message ' + message + ' - ' + ex );
                    }
                    if( decoded !== undefined ) {
                        return previous( intopic, decoded );
                    }
                };
            }
        }

        // send through codec's decode function
        let codecDecode = getCodecFunction( codec, property, 'decode' );
        if( codecDecode ) {
            console.log("warning, doing codecDecode");
            let realHandler = handler;
            let output = function( message ) {
                return realHandler( topic, message );
            };
            handler = function( intopic, message ) {
                console.log("in codec handler");
                let decoded = codecDecode( message, { topic, property, extendedTopic }, output );
                if( config.logMqtt ) {
                    log( 'codec decoded message to [' + decoded + ']' );
                }
                if( decoded !== undefined ) {
                    return output( decoded );
                }
            };
        }

        // register property dispatch (codec only)
        if( codec ) {
            console.log("warning, codec exists");
            if( propDispatch.hasOwnProperty( property ) ) {
                // new handler for existing property
                propDispatch[ property ].push( rawHandler );
            } else {
                // new property
                propDispatch[ property ] = [ rawHandler ];
                if( ctx.config.logMqtt ) {
                    log( 'Avalable codec notification property: ' + property );
                }
            }
        }

        // JSONPath
        //console.log("$ topic: ", topic);
        const jsonpathIndex = topic?.indexOf( '/' ) ?? -1;
        //console.log("jsonpathIndex: ", jsonpathIndex);
        if( jsonpathIndex > 0 ) {
            let jsonpathQuery = topic; //topic.substring( jsonpathIndex );
            //topic = topic.substring( 0, jsonpathIndex );

            const lastHandler = handler;
            handler = function( intopic, message ) {
                //console.log("lastHandler: ", intopic, message);
                //const json = JSON.parse( message );
                //const output = [{"value":message}];
                //console.log("typeof message: ", typeof message);
                const output = [message];
                //{"name": "flex_lamp", "service_name": "light", "characteristic": "On", "value": true}
                //const values = jsonpath.query( json, jsonpathQuery );
                //const output = values.shift();
                //if( config.logMqtt ) {
                //log( `jsonpath ${jsonpathQuery} decoded message to [${output}]` );
                //}
                
                return lastHandler( topic, output );
            };
        }
        else{
            console.log("ERROR, no handler now");
        }

        // register MQTT dispatch and subscribe
        if( mqttDispatch.hasOwnProperty( topic ) ) {
            //console.log("new handler for existing topic: ", topic);
            // new handler for existing topic
            mqttDispatch[ topic ].push( handler );
        } else {
            //console.log("new topic: ", topic);
            // new topic
            mqttDispatch[ topic ] = [ handler ];
            //mqttClient.subscribe(topic);
        }
    };

    // Publish
    this.publish = function( ctx, topic, property, message ) {
        console.log("mqttlib: in publish. topic: ", topic);
        // let { log, mqttClient, codec } = ctx;
        let { log, codec } = ctx;
        /*
        if( ! mqttClient ) {
            log( 'ERROR: Call mqttlib.init() before mqttlib.publish()' );
            return;
        }
        */

        if( message === null || topic === undefined ) {
            console.error("this.publish: missing message or topic");
            return; // don't publish if message is null or topic is undefined
        }

        let extendedTopic = null;
        // first of all, pass message through any user-supplied apply() function
        if (typeof topic != 'string') {
            // encode data with user-supplied apply() function
            extendedTopic = topic;
            topic = extendedTopic.topic;
            if (extendedTopic.hasOwnProperty('apply')) {
                var applyFn = Function( "message", "state", extendedTopic['apply'] ); //eslint-disable-line
                try {
                    message = applyFn( message, getApplyState( ctx, property ) );
                } catch( ex ) {
                    log( 'Encode function apply( message ) { ' + extendedTopic.apply + ' } failed for topic ' + topic + ' with message ' + message + ' - ' + ex );
                    message = null; // stop publish
                }
                if( message === null || message === undefined ) {
                    return;
                }
            }
        }

        function publishImpl( finalMessage ) {
            optimizedPublish( topic, finalMessage, ctx );
        }

        // publish directly or through codec
        let codecEncode = getCodecFunction( codec, property, 'encode' );
        if( codecEncode ) {
            // send through codec's encode function
            let encoded = codecEncode( message, { topic, property, extendedTopic }, publishImpl );
            if( encoded !== undefined ) {
                publishImpl( encoded );
            }
        } else {
            // publish as-is
            publishImpl( message );
        }
    };

    // Confirmed publisher
    this.makeConfirmedPublisher = function( ctx, setTopic, getTopic, property, makeConfirmed ) {
        console.log("mqttlib: in makeConfirmedPublisher. setTopic: ", setTopic);
        let { state, config, log } = ctx;

        // if confirmation isn't being used, just return a simple publishing function
        if( ! config.confirmationPeriodms || ! getTopic || ! makeConfirmed ) {
            //console.log("returning a simple publishing function");
            // no confirmation - return generic publishing function
            return function( message ) {
                mqttlib.publish( ctx, setTopic, property, message );
            };
        }
        else{
            console.log("doing complex confirmation...");
        }

        var timer = null;
        var expected = null;
        var indicatedOffline = false;
        var retriesRemaining = 0;

        // subscribe to our get topic
        mqttlib.subscribe( ctx, getTopic, property, function( topic, message ) {
            if( ( message === expected || message == ( expected + '' ) ) && timer ) {
                clearTimeout( timer );
                timer = null;
            }
            if( indicatedOffline && ! timer ) {
                // if we're not waiting (or no-longer waiting), a message clears the offline state
                state.online = true;
                indicatedOffline = false;
                log( 'Setting accessory state to online' );
            }
        } );

        // return enhanced publishing function
        return function( message ) {
            // clear any existing confirmation timer
            if( timer ) {
                clearTimeout( timer );
                timer = null;
            }

            // confirmation timeout function
            function confirmationTimeout() {
                // confirmation period has expired
                timer = null;
                // indicate offline (unless accessory is publishing this explicitly - overridden with confirmationIndicateOffline)
                if( config.confirmationIndicateOffline !== false && ( ! config.topics.getOnline || config.confirmationIndicateOffline === true ) && ! indicatedOffline ) {
                    state.online = false;
                    indicatedOffline = true;
                    log( 'Setting accessory state to offline' );
                }

                // retry
                if( retriesRemaining > 0 ) {
                    --retriesRemaining;
                    publish();
                } else {
                    log( 'Unresponsive - no confirmation message received on ' + getTopic + ". Expecting [" + expected + "]." );
                }
            }

            function publish() {
                // set confirmation timer
                timer = setTimeout( confirmationTimeout, config.confirmationPeriodms );

                // publish
                expected = message;
                mqttlib.publish( ctx, setTopic, property, message );
            }

            // initialise retry counter
            retriesRemaining = ( config.retryLimit === undefined ) ? 3 : config.retryLimit;

            // initial publish
            publish();
        };
    };

};

module.exports = mqttlib;
