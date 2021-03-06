"""Example wirth separate thread for processdata"""

import sys
import struct
import time
import threading

from collections import namedtuple

import pysoem

class ThreadingExample:

    BECKHOFF_VENDOR_ID = 0x0002
    EK1100_PRODUCT_CODE = 0x044c2c52
    EL4008_PRODUCT_CODE = 0x0FA83052
    EL4114_PRODUCT_CODE = 0x10123052
    EL3144_PRODUCT_CODE = 0x0C483052
    EL2624_PRODUCT_CODE = 0x0A403052
    EL2872_PRODUCT_CODE = 0x0B383052
    EL1872_PRODUCT_CODE = 0x07503052

    # Constructor
    def __init__(self, ifname):
        self._ifname = ifname
        self._pd_thread_stop_event = threading.Event()
        self._ch_thread_stop_event = threading.Event()
        self._actual_wkc = 0
        self._master = pysoem.Master()
        self._master.in_op = False
        self._master.do_check_state = False
        SlaveSet = namedtuple('SlaveSet', 'name product_code config_func')
        self._expected_slave_layout = {0: SlaveSet('EK1100', self.EK1100_PRODUCT_CODE, None),
                                       1: SlaveSet('EL4008', self.EL4008_PRODUCT_CODE, None),
                                       2: SlaveSet('EL4114', self.EL4114_PRODUCT_CODE, None),
                                       3: SlaveSet('EL3144', self.EL3144_PRODUCT_CODE, None),
                                       4: SlaveSet('EL2624', self.EL2624_PRODUCT_CODE, None),
                                       5: SlaveSet('EL2872', self.EL2872_PRODUCT_CODE, self.el2872_setup),
                                       6: SlaveSet('EL1872', self.EL1872_PRODUCT_CODE, None)}

    # Setup function for EL2872
    def el2872_setup(self, slave_pos):
        # Obtain relevant slave object from master
        slave = self._master.slaves[slave_pos]

        # Set DC sync - Use / Purpose ??
        slave.dc_sync(1, 10000000)

    # Static method to check state of slave (will be executed in separate thread)
    @staticmethod
    def _check_slave(slave, pos):
        # SAFEOP && ERROR
        if slave.state == (pysoem.SAFEOP_STATE + pysoem.STATE_ERROR):
            print('ERROR : Slave {} is in SAFE_OP + ERROR, attempting to acknowledge...'.format(pos))
            slave.state = pysoem.SAFEOP_STATE + pysoem.STATE_ACK
            slave.write_state()
        # SAFEOP_STATE
        elif slave.state == pysoem.SAFEOP_STATE:
            print('WARNING : Slave {} is in SAFE_OP, trying to change to OPERATIONAL...'.format(pos))
            slave.state = pysoem.OP_STATE
            slave.write_state()
        # NONE_STATE
        elif slave.state > pysoem.NONE_STATE:
            if slave.reconfig():
                slave.is_lost = False
                print('MESSAGE : Slave {} reconfigured...'.format(pos))
        # Check if slave is lost
        elif not slave.is_lost:
            slave.state_check(pysoem.OP_STATE)
            if slave.state == pysoem.NONE_STATE:
                slave.is_lost = True
                print('ERROR : Slave {} lost...'.format(pos))
        # If lost, trying to recover
        if slave.is_lost:
            if slave.state == pysoem.NONE_STATE:
                if slave.recover():
                    # Recovery successful
                    slave.is_lost = False
                    print('MESSAGE : Slave {} recovered...'.format(pos))
            else:
                # ??
                slave.is_lost = False
                print('MESSAGE : Slave {} found...'.format(pos))
    
    # Thread for checking slave states
    # Timing: 10 ms (+ execution time)
    # (Pre-) Condition:
    # - Master is IN_OP
    # Trigger for check:
    # - WKC counter less than expected
    # - do_check_state is set to TRUE
    def _check_thread(self):
        # Check if thread stop event is set
        while not self._ch_thread_stop_event.is_set():
            if self._master.in_op and ((self._actual_wkc < self._master.expected_wkc) or self._master.do_check_state):
                self._master.do_check_state = False
                self._master.read_state()
                for i, slave in enumerate(self._master.slaves):
                    if slave.state != pysoem.OP_STATE:
                        self._master.do_check_state = True
                        ThreadingExample._check_slave(slave, i)
                if not self._master.do_check_state:
                    print('OK: All slaves resumed OPERATIONAL.')
            time.sleep(0.01)

    # Thread for continuously running the send and rec'v processdata cmds
    # Timing: 10 ms (+ execution time)
    def _processdata_thread(self):
        # Check if thread stop event is set
        while not self._pd_thread_stop_event.is_set():
            self._master.send_processdata()
            self._actual_wkc = self._master.receive_processdata(10000)
            
            # Testing Toggle Bit an der EL3144
            # https://infosys.beckhoff.de/index.php?content=../content/1031/el31xx/1710364299.html&id=
            # el3144_ch_all_current_as_bytes = self._master.slaves[3].input
            # el3144_ch_all_current_as_int16_struct = struct.unpack('8H', el3144_ch_all_current_as_bytes)
            # el3144_ch_1_state_as_int16 = el3144_ch_all_current_as_int16_struct[0]
            # print('{:#06x}'.format(el3144_ch_1_state_as_int16))
            
            if not self._actual_wkc == self._master.expected_wkc:
                print('Incorrect WKC')
            time.sleep(0.005)

    # Continuously running loop toggling the DOs until interrupted with Ctrl + C
    def _pdo_update_loop(self):
        # Set MASTER to "in operation"
        self._master.in_op = True

        # Initialize toggle variable
        toggle = True

        # Try the permanent loop
        try:
            while 1:
                # Struct erforderlich, da Bytes erwartet werden und keine Ints oder ähnliches
                print('Setting:')
                if toggle:
                    # Signed 16bit (Struct: shirt - "h"): -32768 .. 32767
                    # 1.0V: f3276.7 = d3277 = 0x0CCD
                    # 1.5V: f4915.05 = d4915 = 0x1333
                    # 2.0V: f6553,4 = d6553 = 0x1999
                    # 2.5V: f8191.75 = d8192 = 0x2000
                    # 3.0V: f9830,1 = d9830 = 0x2666
                    # 3.5V: f11468,45 = d11468 = 0x2CCC
                    # 4.0V: f13106,8 = d13106 = 0x3332
                    # 4.5V: f14745,15 = d14745 = 0x3999
                    # 7.5V: f24575.25 = d24575 = 0x5FFF
                    self._master.slaves[1].output = struct.pack('8h', 0x0CCD, 0x1999, 0x2666, 0x3332, 0x0CCD, 0x1999, 0x2666, 0x3332)
                    print('EL4008: 1V, 2V, 3V, 4V, 1V, 2V, 3V, 4V')
                else:
                    self._master.slaves[1].output = struct.pack('8h', 0x1333, 0x2000, 0x2CCC, 0x3999, 0x1333, 0x2000, 0x2CCC, 0x3999)
                    print('EL4008: 1.5V, 2.5V, 3.5V, 4.5V, 1.5V, 2.5V, 3.5V, 4.5V')
                print('**********')
                if toggle:
                    # Signed 16bit (Struct: shirt - "h"): -32768 .. 32767
                    # 4 mA: f6553,4 = d6553 = 0x1999
                    # 8 mA: f13106,8 = d13106 = 0x3332
                    # 12 mA: f19660,2 = d19660 = 0x4CCC
                    # 16 mA: f26213,6 = d26214 = 0x6666
                    # 20 mA: f32767 = d32767 = 0x7FFF
                    self._master.slaves[2].output = struct.pack('4h', 0x1999, 0x3332, 0x4CCC, 0x6666)
                    print('EL4114: 4mA, 8mA, 12mA, 16mA')
                else:
                    self._master.slaves[2].output = struct.pack('4h', 0x3332, 0x1999, 0x6666, 0x4CCC)
                    print('EL4114: 8mA, 4mA, 16mA, 12mA')
                print('**********')
                if toggle:
                    self._master.slaves[4].output = struct.pack('B', 0x05)
                    print('EL2624: 0x05 = Relais 1 + 3')
                else:
                    self._master.slaves[4].output = struct.pack('B', 0x0A)
                    print('EL2624: 0x0A = Relais 2 + 4')
                print('**********')
                # Toggle outputs between 1-3-5-7-9-11-13-15 and 2-4-6-8-10-12-14-16
                if toggle:
                    self._master.slaves[5].output = struct.pack('H', 0xAAAA)
                    print('EL2872: 0xAAAA = all right')
                else:
                    self._master.slaves[5].output = struct.pack('H', 0x5555)
                    print('EL2872: 0x5555 = all left')

                print('=================================================')
                # Wait for propagation of physical signals (especially DO to DI)
                time.sleep(0.01)
                print('Reading:')

                # Read from INPUTs
                # EL3144 - 4 Channels, je 16 Bit Analog Value und 16 Bit Status
                # 16 Bit Status: erstes Bit toggelt zwischen jedem gelesenen Analog-Wert (also zwischen 0x8000 und 0x0000)
                print('EL3144: {}'.format(self._master.slaves[3].input.hex()))
                el3144_ch_all_current_as_bytes = self._master.slaves[3].input
                el3144_ch_all_current_as_int16_struct = struct.unpack('8h', el3144_ch_all_current_as_bytes)

                el3144_ch_1_state_as_int16 = el3144_ch_all_current_as_int16_struct[0]
                el3144_ch_1_current_as_int16 = el3144_ch_all_current_as_int16_struct[1]
                
                el3144_ch_2_state_as_int16 = el3144_ch_all_current_as_int16_struct[2]
                el3144_ch_2_current_as_int16 = el3144_ch_all_current_as_int16_struct[3]
                
                el3144_ch_3_state_as_int16 = el3144_ch_all_current_as_int16_struct[4]
                el3144_ch_3_current_as_int16 = el3144_ch_all_current_as_int16_struct[5]
                
                el3144_ch_4_state_as_int16 = el3144_ch_all_current_as_int16_struct[6]
                el3144_ch_4_current_as_int16 = el3144_ch_all_current_as_int16_struct[7]
                
                el3144_ch_1_current = el3144_ch_1_current_as_int16 * 10 / 0x8000
                el3144_ch_2_current = el3144_ch_2_current_as_int16 * 10 / 0x8000
                el3144_ch_3_current = el3144_ch_3_current_as_int16 * 10 / 0x8000
                el3144_ch_4_current = el3144_ch_4_current_as_int16 * 10 / 0x8000

                print('EL3144: Ch 1 PDO: {:#06x}; Current: {:.6}; State: {:#06x}'.format(el3144_ch_1_current_as_int16, el3144_ch_1_current, el3144_ch_1_state_as_int16))
                print('EL3144: Ch 2 PDO: {:#06x}; Current: {:.6}; State: {:#06x}'.format(el3144_ch_2_current_as_int16, el3144_ch_2_current, el3144_ch_2_state_as_int16))
                print('EL3144: Ch 3 PDO: {:#06x}; Current: {:.6}; State: {:#06x}'.format(el3144_ch_3_current_as_int16, el3144_ch_3_current, el3144_ch_3_state_as_int16))
                print('EL3144: Ch 4 PDO: {:#06x}; Current: {:.6}; State: {:#06x}'.format(el3144_ch_4_current_as_int16, el3144_ch_4_current, el3144_ch_4_state_as_int16))

                print('**********')

                el1872_ch_all_as_bytes = self._master.slaves[6].input
                el1872_ch_all_as_int16 = struct.unpack('H', el1872_ch_all_as_bytes)[0]
                print('EL1872: {:#06x} - {:#018b}'.format(el1872_ch_all_as_int16, el1872_ch_all_as_int16))

                print('===========================================================================================')

                # Invert value of toggle
                toggle ^= True
                # Wait 1 sec
                time.sleep(3)

        except KeyboardInterrupt:
            # Ctrl-C to abort handling
            print('PDO_Update_Loop stopped')
            print('===========================================================================================')

    # Run method of class > called from main()
    def run(self):
        
        print('===========================================================================================')

        # Start EtherCAT MASTER
        self._master.open(self._ifname)
        print("EtherCAT master created and started ...")
        print('===========================================================================================')

        # Do Config_Init and exit, if not successful
        if not self._master.config_init() > 0:
            self._master.close()
            raise ThreadingExampleError('No slaves found')

        # Check if connected slaves are as specified in "_expected_slave_layout"
        for i, slave in enumerate(self._master.slaves):
            if not ((slave.man == self.BECKHOFF_VENDOR_ID) and
                    (slave.id == self._expected_slave_layout[i].product_code)):
                # If not as specified, stop MASTER and raise error
                self._master.close()
                raise ThreadingExampleError('Unexpected slaves layout')
            # Otherwise: Run specified config function and set slave as IS_LOST = FALSE
            slave.config_func = self._expected_slave_layout[i].config_func
            slave.is_lost = False

        # ToDo: Add PDO config here ????

        # Build IOMap > should bring all slaves to SAFEOP_STATE
        self._master.config_map()

        # Check if all slaves reached SAFEOP_STATE
        if self._master.state_check(pysoem.SAFEOP_STATE, 50000) != pysoem.SAFEOP_STATE:
            # Otherwise: stop MASTER and raise error
            self._master.close()
            raise ThreadingExampleError('Not all slaves reached SAFEOP state')
        else:
            print('Transistioned system to SAFEOP_STATE')
            print('===========================================================================================')

        # Prepare transistion to OP_STATE (NO TRANSISTION YET, seperate threads will be started first)
        self._master.state = pysoem.OP_STATE

        # Start Check_Thread
        check_thread = threading.Thread(target=self._check_thread)
        check_thread.start()
        # Start ProcessData_Thread
        proc_thread = threading.Thread(target=self._processdata_thread)
        proc_thread.start()

        # Push STATE change
        self._master.write_state()
        print('Request SYSTEM to OP_STATE via MASTER')
        print('===========================================================================================')

        # Checking if all slaves followed into OP_STATE
        all_slaves_reached_op_state = False
        # Try 40-times (with time-out of 50 ms)
        for i in range(40):
            self._master.state_check(pysoem.OP_STATE, 50000)
            if self._master.state == pysoem.OP_STATE:
                all_slaves_reached_op_state = True
                print('SYSTEM reached OP_STATE')
                print('===========================================================================================')
                break

        # If system reached OP_STATE, start PDO_Update_Loop
        if all_slaves_reached_op_state:
            self._pdo_update_loop()

        # Shutdown
        print('SHUTDOWN initiated')
        print('===========================================================================================')

        # After stopping PDO_Update_Loop with Ctrl+C, system will be shutdown by stopping seperate threads 
        # and transistioning to INIT_STATE
        self._pd_thread_stop_event.set()
        self._ch_thread_stop_event.set()
        # Blocking wait for threads to terminate after setting stop_event for both threads
        # stop_event IS_SET stops while loops in threads
        proc_thread.join()
        check_thread.join()

        # Request INIT state for all slaves
        self._master.state = pysoem.INIT_STATE
        self._master.write_state()
        print('Request SYSTEM to INIT via MASTER')
        print('===========================================================================================')
        
        # Stop EtherCAT MASTER
        self._master.close()
        print("EtherCAT master stopped and closed ...")
        print('===========================================================================================')

        if not all_slaves_reached_op_state:
            raise ThreadingExampleError('Not all slaves reached OP state')

# Separate class for errors
class ThreadingExampleError(Exception):
    def __init__(self, message):
        super(ThreadingExampleError, self).__init__(message)
        self.message = message

# Main fct
if __name__ == '__main__':

    print('Threading example started')

    if len(sys.argv) > 1:
        try:
            ThreadingExample(sys.argv[1]).run()
        except ThreadingExampleError as expt:
            print('Threading example failed: ' + expt.message)
            sys.exit(1)
    else:
        print('Usage: separate_thread ifname')
        sys.exit(1)