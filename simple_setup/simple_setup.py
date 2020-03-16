"""Read from modules"""

import sys
import time
import struct
import pysoem

SDO_Info_Check = False

def read_values(ifname):

    # Create EtherCAT master instance
    master = pysoem.Master()
    
    # Open EtherCAT master instance
    master.open(ifname)
    print("EtherCAT master created and started...")

    print("Enumarating slaves")
    print('===========================================================================================')
    # Enumerate and init all slaves
    if master.config_init() > 0:

        # Read state of all slaves at start-up
        master.read_state()

        # Iterate over all slves found
        for slave in master.slaves:
            # Print info on slave
            print('{}:'.format(slave.name))

            # Read state of slave
            print('\tState: {}'.format(hex(slave.state)))

            if (SDO_Info_Check):
                # Check if SDO info is available
                try:
                    od = slave.od
                except pysoem.SdoInfoError:
                    print('\tno SDO info')
                else:
                    for obj in od:
                        print(' Idx: {}; Code: {}; Type: {}; BitSize: {}; Access: {}; Name: "{}"'.format(
                            hex(obj.index),
                            obj.object_code,
                            obj.data_type,
                            obj.bit_length,
                            hex(obj.obj_access),
                            obj.name))
                        for i, entry in enumerate(obj.entries):
                            if entry.data_type > 0 and entry.bit_length > 0:
                                print('  Subindex {}; Type: {}; BitSize: {}; Access: {} Name: "{}"'.format(
                                    i,
                                    entry.data_type,
                                    entry.bit_length,
                                    hex(entry.obj_access),
                                    entry.name))

        print('===========================================================================================')
        # Transition MASTER to SAFEOP_STATE
        # PREOP_STATE to SAFEOP_STATE request - each slave's config_func is called
        print('Transition sytem to SAFEOP_STATE')
        print('===========================================================================================')
        io_map_size = master.config_map()
        print('IOMap-Size: {}'.format(io_map_size))
        print('===========================================================================================')
        # Config DC
        print('Config DC')
        # print(master.config_dc())
        print('===========================================================================================')
        # DC Sync
        print('DC Sync')
        # master.slaves[3].dc_sync(1,1000000000)
        print('===========================================================================================')

        # wait 50 ms for all slaves to reach SAFE_OP state
        if master.state_check(pysoem.SAFEOP_STATE, 50000) != pysoem.SAFEOP_STATE:
            master.read_state()
            for slave in master.slaves:
                if not slave.state == pysoem.SAFEOP_STATE:
                    print('{} did not reach SAFEOP state'.format(slave.name))
                    print('al status code {} ({})'.format(hex(slave.al_status), pysoem.al_status_code_to_string(slave.al_status)))
            raise Exception('not all slaves reached SAFEOP state')

        # Iterate over all slves found
        for slave in master.slaves:
            # Print info on slave
            print('{}:'.format(slave.name))

            # Read state of slave
            print('\tState: {}'.format(hex(slave.state)))
        print('===========================================================================================')

        # Send and receive process data to have valid data at all outputs before transistioning to OP_STATE
        print('Send and receive process data to have valid data at all outputs before transistioning to OP_STATE')
        master.send_processdata()
        actual_wkc = master.receive_processdata(2000)
        if not actual_wkc == master.expected_wkc:
            print('incorrect wkc')

        print('===========================================================================================')
        
        # Transition MASTER to OP_STATE (Slave should follow)
        print('Transistioning system to OP_STATE')
        master.state = pysoem.OP_STATE
        master.write_state()
        print('===========================================================================================')

        master.state_check(pysoem.OP_STATE, 50000)
        if master.state != pysoem.OP_STATE:
            master.read_state()
            for slave in master.slaves:
                if not slave.state == pysoem.OP_STATE:
                    print('{} did not reach OP state'.format(slave.name))
                    print('al status code {} ({})'.format(hex(slave.al_status), pysoem.al_status_code_to_string(slave.al_status)))
            raise Exception('Not all slaves reached OP state')

        # Read state of all slaves at start-up
        master.read_state()

        # Iterate over all slves found
        for slave in master.slaves:
            # Print info on slave
            print('{}:'.format(slave.name))

            # Read state of slave
            print('\tState: {}'.format(hex(slave.state)))
        print('===========================================================================================')

        # ================= SYSTEM OPERATIONAL ==============================

        # Create individual objects
        M_00 = master.slaves[0]
        # M_01 = master.slaves[1]
        # M_02 = master.slaves[2]
        # M_03 = master.slaves[3]
        print('Waiting 3 secs...')
        time.sleep(3)

        for ii in range(50000):
            print('===========================================================================================')
            print(ii)
            
            master.slaves[3].output = struct.pack('H', 0xAAAA)
            master.send_processdata()
            actual_wkc = master.receive_processdata(2000)
            if not actual_wkc == master.expected_wkc:
                print('incorrect wkc')
            print(master.slaves[3].output.hex())
            print(master.slaves[4].input.hex())

            master.read_state()
            # Iterate over all slves found
            for slave in master.slaves:
                # Print info on slave
                print('{}:'.format(slave.name))

                # Read state of slave
                print('\tState: {}'.format(hex(slave.state)))

            time.sleep(1)
            
            master.slaves[3].output = struct.pack('H', 0x5555)
            master.send_processdata()
            master.receive_processdata(2000)
            if not actual_wkc == master.expected_wkc:
                print('incorrect wkc')
            print(master.slaves[3].output.hex())
            print(master.slaves[4].input.hex())
            
            time.sleep(1)


        #for _ in range(5):
        #    # Write to 1010 1010 1010 1010
        #    master.slaves[5].output = struct.pack('H', 0xAAAA)
        #    time.sleep(0.5)
        #    print(master.slaves[6].input)
        #    time.sleep(3)
            
        #    # Write to 0101 0101 0101 0101‬
        #    master.slaves[5].output = struct.pack('H', 0x5555)
        #    time.sleep(0.5)
        #    print(master.slaves[6].input)
        #    time.sleep(3)


        # Write Analog Output Ch.1 of EL4008 (position 1) to 5V
        # M_01.sdo_write(0x7000, 1, struct.pack('H', 2048))

        time.sleep(1)

        print('===========================================================================================')
        # ================= SHUTDOWN =======================================
        # Transition MASTER to INIT (Slave should follow)
        print('Transistioning system to INIT_STATE')
        master.state = pysoem.INIT_STATE
        master.write_state()

        # Read state of all slaves
        time.sleep(3)

        master.read_state()
        # Iterate over all slves found
        for slave in master.slaves:
            # Print info on slave
            print('{}:'.format(slave.name))

            # Read state of slave
            print('\tState: {}'.format(hex(slave.state)))
        print('===========================================================================================')

    # IF NO SLAVES AVAILABLE !!
    else:
        print('no slave available')

    master.close()

if __name__ == '__main__':

    print('script started')

    if len(sys.argv) > 1:
        read_values(sys.argv[1])
    else:
        print('give ifname as script argument')