#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import frida
import time
import re

def on_message(message, data):
	if message['type'] == 'error':
		print('[!] ' + message['stack'])
	elif message['type'] == 'send':
		print('[i] ' + message['payload'])
	else:
		print(message)

def main(target_process, usb, old_value, new_value, endianness, signed, bits):
	try:
		if usb:
			session = frida.get_usb_device().attach(target_process)
		else:
			session = frida.attach(target_process)
	except:
		sys.exit('An error ocurred while attaching with the procces')
	script = session.create_script("""
		function get_pattern(number, isLittleEndian, bits, signed) {
			var negative = (number < 0 && signed == "s");
			if (number < 0) {
				number *= -1;
			}

			var hex_string = number.toString(16);
			if (hex_string.length %% 2 == 1) {
				hex_string = '0' + hex_string;
			}
			var pattern = "";
			hex_string.match(/.{2}/g).forEach(function(byte) {
				pattern = (isLittleEndian ? byte + " " + pattern : pattern + " " + byte);
			});
			if (isLittleEndian) {
				pattern = pattern.substring(0, pattern.length - 1);
			}
			else {
				pattern = pattern.substring(1, pattern.length);
			}

			var cantBytes = pattern.split(" ").length;
			var bytesReg = Math.floor(bits/8);
			for (i = 0; i < (bytesReg - cantBytes); i++) {
				pattern = (isLittleEndian ? pattern + ' 00' : '00 ' + pattern);
			}
			var lenPattern = pattern.length;
			if (negative) {
				if (isLittleEndian) {
					var prev = pattern.substring(lenPattern-1, lenPattern);
					var nvo = parseInt(prev);
					nvo |= 256;
					nvo = nvo.toString();
					pattern = pattern.substring(0, lenPattern-1) + nvo;
				}
				else {
					var prev = pattern.substring(0, 2);
					var nvo = parseInt(prev);
					nvo |= 256;
					nvo = nvo.toString();
					pattern = nvo + pattern.substring(2);
				}
			}
			return pattern;
		}

		function get_byte_array(number, isLittleEndian, bits, signed) {
			var pattern = get_pattern(number, isLittleEndian, bits, signed);
			var byte_array = [];
			var bytes = pattern.split(" ");
			for (var i = bytes.length - 1; i >= 0; i--) {
				byte_array.push(parseInt("0x" + bytes[i]));
			}
			return byte_array.reverse();
		}		
		var old_value = %d;
		var new_value = %d;
		var isLittleEndian = '%s' == "l";
		var signed = '%s';
		var bits = %d;
		var pattern = get_pattern(old_value, isLittleEndian, bits, signed);
		var new_pattern = get_pattern(new_value, isLittleEndian, bits, signed);
		var byte_array = get_byte_array(new_value, isLittleEndian, bits, signed);

		console.log("[i] searching for " + pattern);
		console.log("[i] replacing for " + new_pattern);

		var ranges = Process.enumerateRangesSync({protection: 'rw-', coalesce: true});
		
		for (var i = 0, len = ranges.length; i < len; i++)
		{
			Memory.scan(ranges[i].base, ranges[i].size, pattern, {
				onMatch: function(address, size) {
					console.log("[+] found at " + address);
					Memory.writeByteArray(address, byte_array);
				},
				onError: function(reason) {
					//console.log('[!] There was an error scanning memory:' + reason);
				},
				onComplete: function() {
					//
				}
			});
		}
""" % (old_value, new_value, endianness, signed, bits))

	script.on('message', on_message)
	script.load()
	time.sleep(3)
	session.detach()

if __name__ == '__main__':
	argc = len(sys.argv)
	if argc < 4 or argc > 9:
		usage = 'Usage: {} [-U] [-e little|big] [-b 64|32|16|8] <process name or PID> <old value> <new value>\n'.format(__file__)
		usage += 'The \'-U\' option is for mobile instrumentation.\n'
		usage += 'The \'-e\' option is to specify the endianness. Little is the default.\n'
		usage += 'The \'-b\' option is to specify the size of the variable in bits. 32 is the default.\n'
		# usage += 'Specify if the variable is signed or unsigned with -s or -u.\n'
		sys.exit(usage)

	usb = False
	endianness = 'l'
	bits = 32
	signed = 'u'
	for i in range(1, argc):
		if sys.argv[i] == '-U':
			usb = True
		elif sys.argv[i] == '-e':
			endianness = sys.argv[i + 1][0]
		elif sys.argv[i] == '-b':
			bits = int(sys.argv[i + 1])

	if sys.argv[argc - 3].isdigit():
		target_process = int(sys.argv[argc - 3])
	else:
		target_process = sys.argv[argc - 3]

	old_value = int(sys.argv[argc - 2])

	new_value = int(sys.argv[argc - 1])

	if old_value < 0 or new_value < 0:
		sys.exit('Negative numbers aren\'t suported yet.')

	if (old_value > (2 ** (bits - 1)) - 1 and signed == 's') or (old_value > (2 ** bits) - 1 and signed == 'u'):
		sys.exit(str(old_value) + ' is too large')

	if (new_value > (2 ** (bits - 1)) - 1 and signed == 's') or (new_value > (2 ** bits) - 1 and signed == 'u'):
		sys.exit(str(new_value) + ' is too large')

	main(target_process, usb, old_value, new_value, endianness, signed, bits)
