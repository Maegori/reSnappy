from typing import Optional
from paramiko import SSHClient
import numpy as np
import lz4.frame
import cv2 as cv
import argparse
import sys

parser = argparse.ArgumentParser(description="Screenshot and crop the reMarkable tablet")
parser.add_argument('-s', 
                    help = "IP-adress of the reMarkabel tablet, default:10.11.99.1",
                    default = "10.11.99.1",
                    type = str)
parser.add_argument('-inv',
                    help = "Wether or not to invert the colors of the screenshot.",
                    dest = 'invert',
                    action='store_true', 
                    required=False)
parser.add_argument('-o',
                    help = "Name of the output file, without the extension",
                    default = "temp",
                    type = str)

rm1_specs = {'width' : 1408,
             'heigth' : 1872,
             'bytes_per_pixel' : 2}

rm2_specs = {'width' : 1872,
             'heigth' : 1404,
             'bytes_per_pixel' : 1}

def get_version(ssh_client:SSHClient) -> int:
    """
    Returns Remarkable version, either 1 or 2, as integer
    """

    cmd = 'cat /sys/devices/soc0/machine'
    _, stdout, _ = ssh_client.exec_command(cmd)
    out = stdout.readlines()
    version = out[0].split('\\')[0]

    if '1' in version:
        return 1
    elif '2' in version:
        return 2
    else:
        print('Your machine is not recognized, exitting...')
        ssh_client.close()
        sys.exit()

def get_pid(ssh_client:SSHClient) -> str:
    """
    Returns the pid of the xochitl process, if there are multiple,
    return the first one which contains /dev/fb0.
    """
    _, stdout, _ =ssh_client.exec_command('pidof xochitl')

    for out in stdout.readlines():
        pid = out.split('\\')[0][:-1]
        _, has_fb, _ = ssh_client.exec_command(f"grep -C1 /dev/fb0 /proc/{pid}/maps")
        if len(has_fb.readlines()) > 0:
            return pid

def remove_toolbar(img:np.ndarray) -> np.ndarray:
    """
    Takes the screenshot from the reMarkable and checks if the
    toolbar is present, if so, it removes it and returns the resulting
    image.
    """

    # remove menu and indicators
    menu_is_open = (img[52:58, 52:58] == 0).all()
    if menu_is_open:
        # remove the entire menu, and the x in the top right corner
        img[:, :120] = 255
        img[39:80, 1324:1364] = 255
    else:
        # remove only the menu indicator circle
        img[39:81, 40:81] = 255

    return img

def crop_image(img:np.ndarray, invert:bool) -> np.ndarray:
    """
    Inverts and crops the screenshot from the reMarkable to only its
    drawing.
    """

    # find drawn figure on the screenshot
    img = cv.bitwise_not(img)
    coors = cv.findNonZero(img)
    X = coors[:,0][:,0][:-1]
    Y = coors[:,0][:,1][:-1]
    if not invert:
        img = cv.bitwise_not(img)

    # crop image to drawn part
    img = img[min(Y):max(Y), min(X):max(X)]

    # cv.imshow("test", img)
    # cv.waitKey(0)
    return img


def img_processor(buffer, width, heigth, invert) -> np.ndarray:
    """
    Takes the decompressed binarry data from the
    reMarkable and turns it into an image, also
    peforms preprocessing.
    """

    # convert buffer to image and rotate it upright
    img = np.frombuffer(buffer, dtype=np.uint8).reshape((width, heigth))
    img = cv.rotate(img, cv.ROTATE_90_COUNTERCLOCKWISE)

    # apply image processing
    img = remove_toolbar(img)   
    img = crop_image(img, invert)
    
    # set background to alpha channel
    bg_mask = np.where(img == 255 * (not invert), 0, 255)
    alpha = cv.cvtColor(img, cv.COLOR_GRAY2BGRA)
    alpha[:, :, 3] = bg_mask
    return alpha

def main(host, out_name, invert):
    client = SSHClient()
    client.load_system_host_keys()
    client.connect(hostname = host, username = 'root')

    version = get_version(client)
    pid = get_pid(client)

    # find head
    _, stdout, _ = client.exec_command('find /opt/bin/head')
    if len(stdout.readlines()) == 0:
        print('head could not be found on your machine, refer to the README.')
        client.close()
        sys.exit()
    else:
        head = "/opt/bin/head"

    # find lz4
    _, stdout, _ = client.exec_command('find /opt/bin/lz4')
    out = stdout.readlines()
    if len(out) == 0:
        print('LZ4 could not be found on your machine, refer to the README.')
        client.close()
        sys.exit()
    else:
        compress = "/opt/bin/lz4"
    
    if version == 1:
        specs = rm1_specs
    else:
        specs = rm2_specs

    # calculate the amount of bytes per window
    window_bytes = specs['width'] * specs['heigth'] * specs['bytes_per_pixel']

    # find framebuffer location in memory
    # it is actually the map allocated _after_ the fb0 mmap
    _, stdout, _ = client.exec_command(f"grep -C1 /dev/fb0 /proc/{pid}/maps | tail -n1 | sed 's/-.*$//'")
    skip_bytes_hex = stdout.readlines()[0].split('\\')[0][:-1]
    skip_bytes = int(skip_bytes_hex, 16) + 8

    # carve the framebuffer out of the process memory
    page_size = 4096
    window_start_blocks = round(skip_bytes / page_size)
    window_offset = skip_bytes % page_size
    window_length_blocks = round(window_bytes / page_size) + 1

    # Using dd with bs=1 is too slow, so we first carve out the pages our desired
    # bytes are located in, and then we trim the resulting data with what we need.
    head_fb0 = f"""
    dd if=/proc/{pid}/mem bs={page_size} skip={window_start_blocks} count={window_length_blocks} 2>/dev/null |
    tail -c+{window_offset} |
    {head} -c {window_bytes} |
    {compress}
    """

    # collect the screenshot, decompress it, process it and save it
    _, stdout, _ = client.exec_command(head_fb0)
    buffer = lz4.frame.decompress(stdout.read())
    img = img_processor(buffer, specs['heigth'], specs['width'], invert)
    cv.imwrite(f"{out_name}.png", img)

    client.close()   

if __name__ == "__main__":
    args = vars(parser.parse_args())
    host = args['s']
    out_name = args['o']
    invert = args['invert']
    main(host, out_name, invert)