#!/usr/bin/env python3
'''
Les Wright 21 June 2023
https://youtube.com/leslaboratory
A Python program to read, parse and display thermal data from the Topdon TC001 Thermal camera!
'''
print('Les Wright 21 June 2023')
print('https://youtube.com/leslaboratory')
print('A Python program to read, parse and display thermal data from the Topdon TC001 Thermal camera!')
print('')
print('Tested on Debian all features are working correctly')
print('This will work on the Pi However a number of workarounds are implemented!')
print('Seemingly there are bugs in the compiled version of cv2 that ships with the Pi!')
print('')
print('Key Bindings:')
print('')
print('a z: Increase/Decrease Blur')
print('s x: Floating High and Low Temp Label Threshold')
print('d c: Change Interpolated scale Note: This will not change the window size on the Pi')
print('f v: Contrast')
print('q w: Fullscreen Windowed (note going back to windowed does not seem to work on the Pi!)')
print('r t: Record and Stop')
print('p : Snapshot')
print('m : Cycle through ColorMaps')
print('h : Toggle HUD')

import cv2
import numpy as np
import argparse
import time
import io
import sys

#We need to know if we are running on the Pi, because openCV behaves a little oddly on all the builds!
#https://raspberrypi.stackexchange.com/questions/5100/detect-that-a-python-program-is-running-on-the-pi
def is_raspberrypi():
    try:
        with io.open('/sys/firmware/devicetree/base/model', 'r') as m:
            if 'raspberry pi' in m.read().lower(): return True
    except Exception: pass
    return False

isPi = is_raspberrypi()

def sizeArg(text):
	#parse "WxH", e.g. 640x480
	try:
		w, h = (int(v) for v in text.lower().split('x'))
	except ValueError:
		raise argparse.ArgumentTypeError("expected WxH, e.g. 640x480")
	if w < 16 or h < 16 or w % 2 or h % 2:
		raise argparse.ArgumentTypeError("width and height must be even and at least 16")
	return (w, h)

parser = argparse.ArgumentParser()
parser.add_argument("--device", type=int, default=0, help="Video Device number e.g. 0, use v4l2-ctl --list-devices")
parser.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270], help="Rotate image clockwise by 0, 90, 180 or 270 degrees")
parser.add_argument("--vcam", nargs="?", const="auto", default=None, metavar="DEVICE", help="Also send the processed video to a v4l2loopback device (e.g. /dev/video10) so other programs can use it as a webcam. Without DEVICE the first free loopback device is used. Needs: pip install pyvirtualcam")
parser.add_argument("--vcam-size", type=sizeArg, default=None, metavar="WxH", help="Output size of the virtual webcam, e.g. 640x480 or 1920x1080 (default: 1280x720). The image is scaled to fit and letterboxed, never stretched.")
args = parser.parse_args()

#optional rotation (image AND temperature data are rotated together)
rotateCode = {0: None, 90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}[args.rotate]
rotation = None
if args.rotate == 90:
  rotation = cv2.ROTATE_90_CLOCKWISE
elif args.rotate == 180:
  rotation = cv2.ROTATE_180
elif args.rotate == 270:
  rotation = cv2.ROTATE_90_COUNTERCLOCKWISE
	
if args.device:
	dev = args.device
else:
	dev = 0
	
#init video
cap = cv2.VideoCapture('/dev/video'+str(dev), cv2.CAP_V4L)
#cap = cv2.VideoCapture(0)
#pull in the video but do NOT automatically convert to RGB, else it breaks the temperature data!
#https://stackoverflow.com/questions/63108721/opencv-setting-videocap-property-to-cap-prop-convert-rgb-generates-weird-boolean
if isPi == True:
	cap.set(cv2.CAP_PROP_CONVERT_RGB, 0.0)
else:
	cap.set(cv2.CAP_PROP_CONVERT_RGB, 0.0)

#General settings
#sensor size: taken from the first frame (each frame = image on top + temperature data below)
ret, frame = cap.read()
if ret and frame is not None and frame.ndim == 3:
	print('Camera frame: %dx%d pixels, %d channels (driver reports %dx%d)' % (frame.shape[1], frame.shape[0], frame.shape[2],
		int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))))
	width = frame.shape[1] #Sensor width
	height = frame.shape[0]//2 #sensor height
else:
	width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) #Sensor width
	height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))//2 #sensor height
# if width <= 0 or height <= 0:
	# width, height = 384, 384 #fallback if the camera does not report its size
# width, height = 384, 384 #fallback if the camera does not report its size
# width, height = width*2, height
print('Sensor: %dx%d pixels' % (width, height))
if rotation in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
	width, height = height, width
#raw sensor value -> Celsius: raw/64 - tempOffset (original TC001: 273.15, adjusted for this camera)
tempOffset = 475.15
scale = 3 #scale multiplier
newWidth = width*scale 
newHeight = height*scale
alpha = 1.0 # Contrast control (1.0-3.0)
colormap = 0
font=cv2.FONT_HERSHEY_SIMPLEX
dispFullscreen = False
cv2.namedWindow('Thermal',cv2.WINDOW_GUI_NORMAL)
cv2.resizeWindow('Thermal', newWidth,newHeight)

#optional virtual webcam via v4l2loopback (fixed standard size, independent of the d/c scaling keys)
vcam = None
if args.vcam:
	try:
		import pyvirtualcam
	except ImportError:
		print('Error: --vcam needs the Python package pyvirtualcam:  pip install pyvirtualcam')
		sys.exit(1)
	vcamWidth, vcamHeight = args.vcam_size if args.vcam_size else (1280, 720) #standard webcam resolution
	try:
		vcam = pyvirtualcam.Camera(width=vcamWidth, height=vcamHeight, fps=25,
			fmt=pyvirtualcam.PixelFormat.RGB, backend='v4l2loopback',
			device=None if args.vcam == 'auto' else args.vcam)
	except RuntimeError as e:
		print('Error: could not open the virtual webcam:', e)
		print('Is the v4l2loopback module loaded? e.g.:')
		print('  sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="TC001 Thermal" exclusive_caps=1')
		sys.exit(1)
	print('Virtual webcam: %s (%dx%d @ 25 fps)' % (vcam.device, vcamWidth, vcamHeight))
rad = 0 #blur radius
threshold = 2
hud = True
recording = False
elapsed = "00:00:00"
snaptime = "None"

def rec():
	now = time.strftime("%Y%m%d--%H%M%S")
	#do NOT use mp4 here, it is flakey!
	videoOut = cv2.VideoWriter(now+'output.avi', cv2.VideoWriter_fourcc(*'XVID'),25, (newWidth,newHeight))
	return(videoOut)

def fitToSize(img, outWidth, outHeight):
	#Scale the image into outWidth x outHeight while keeping its aspect ratio (black bars, no stretching)
	h, w = img.shape[:2]
	if (w, h) == (outWidth, outHeight):
		return img
	f = min(outWidth / w, outHeight / h)
	nw, nh = max(1, int(round(w * f))), max(1, int(round(h * f)))
	interp = cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC
	resized = cv2.resize(img, (nw, nh), interpolation=interp)
	canvas = np.zeros((outHeight, outWidth) + img.shape[2:], dtype=img.dtype)
	x0, y0 = (outWidth - nw) // 2, (outHeight - nh) // 2
	canvas[y0:y0+nh, x0:x0+nw] = resized
	return canvas

def snapshot(heatmap):
	#I would put colons in here, but it Win throws a fit if you try and open them!
	now = time.strftime("%Y%m%d-%H%M%S") 
	snaptime = time.strftime("%H:%M:%S")
	cv2.imwrite("TC001"+now+".png", heatmap)
	return snaptime
 

while(cap.isOpened()):
	# Capture frame-by-frame
	ret, frame = cap.read()
	if ret == True:
		imdata,thdata = np.array_split(frame, 2)
		if rotation is not None:
			thdata = cv2.rotate(thdata, rotation)
		thHeight, thWidth = thdata.shape[:2]
		#now parse the data from the bottom frame and convert to temp!
		#https://www.eevblog.com/forum/thermal-imaging/infiray-and-their-p2-pro-discussion/200/
		#Huge props to LeoDJ for figuring out how the data is stored and how to compute temp from it.
		#16 bit raw value per pixel: low byte in channel 0, high byte in channel 1
		rawdata = thdata[...,0].astype(np.uint32) + thdata[...,1].astype(np.uint32)*256

		#grab data from the center pixel...
		rawtemp = int(rawdata[thHeight//2][thWidth//2])
		temp = round((rawtemp/64)-tempOffset, 2)

		#find the max temperature in the frame
		posmax = int(rawdata.argmax())
		#since argmax returns a linear index, convert back to row and col
		mcol,mrow = divmod(posmax,thWidth)
		maxtemp = round((int(rawdata[mcol][mrow])/64)-tempOffset, 2)

		#find the lowest temperature in the frame
		posmin = int(rawdata.argmin())
		lcol,lrow = divmod(posmin,thWidth)
		mintemp = round((int(rawdata[lcol][lrow])/64)-tempOffset, 2)

		#find the average temperature in the frame
		avgtemp = round((float(rawdata.mean())/64)-tempOffset, 2)

		

		# Convert the real image to RGB
		bgr = cv2.cvtColor(imdata,  cv2.COLOR_YUV2BGR_YUYV)
		if rotation is not None:
			bgr = cv2.rotate(bgr, rotation)
		#Contrast
		bgr = cv2.convertScaleAbs(bgr, alpha=alpha)#Contrast
		#bicubic interpolate, upscale and blur
		bgr = cv2.resize(bgr,(newWidth,newHeight),interpolation=cv2.INTER_CUBIC)#Scale up!
		if rad>0:
			bgr = cv2.blur(bgr,(rad,rad))

		#apply colormap
		if colormap == 0:
			heatmap = cv2.applyColorMap(bgr, cv2.COLORMAP_JET)
			cmapText = 'Jet'
		if colormap == 1:
			heatmap = cv2.applyColorMap(bgr, cv2.COLORMAP_HOT)
			cmapText = 'Hot'
		if colormap == 2:
			heatmap = cv2.applyColorMap(bgr, cv2.COLORMAP_MAGMA)
			cmapText = 'Magma'
		if colormap == 3:
			heatmap = cv2.applyColorMap(bgr, cv2.COLORMAP_INFERNO)
			cmapText = 'Inferno'
		if colormap == 4:
			heatmap = cv2.applyColorMap(bgr, cv2.COLORMAP_PLASMA)
			cmapText = 'Plasma'
		if colormap == 5:
			heatmap = cv2.applyColorMap(bgr, cv2.COLORMAP_BONE)
			cmapText = 'Bone'
		if colormap == 6:
			heatmap = cv2.applyColorMap(bgr, cv2.COLORMAP_SPRING)
			cmapText = 'Spring'
		if colormap == 7:
			heatmap = cv2.applyColorMap(bgr, cv2.COLORMAP_AUTUMN)
			cmapText = 'Autumn'
		if colormap == 8:
			heatmap = cv2.applyColorMap(bgr, cv2.COLORMAP_VIRIDIS)
			cmapText = 'Viridis'
		if colormap == 9:
			heatmap = cv2.applyColorMap(bgr, cv2.COLORMAP_PARULA)
			cmapText = 'Parula'
		if colormap == 10:
			heatmap = cv2.applyColorMap(bgr, cv2.COLORMAP_RAINBOW)
			heatmap = cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)
			cmapText = 'Inv Rainbow'

		#print(heatmap.shape)

		# draw crosshairs
		cv2.line(heatmap,(int(newWidth/2),int(newHeight/2)+20),\
		(int(newWidth/2),int(newHeight/2)-20),(255,255,255),2) #vline
		cv2.line(heatmap,(int(newWidth/2)+20,int(newHeight/2)),\
		(int(newWidth/2)-20,int(newHeight/2)),(255,255,255),2) #hline

		cv2.line(heatmap,(int(newWidth/2),int(newHeight/2)+20),\
		(int(newWidth/2),int(newHeight/2)-20),(0,0,0),1) #vline
		cv2.line(heatmap,(int(newWidth/2)+20,int(newHeight/2)),\
		(int(newWidth/2)-20,int(newHeight/2)),(0,0,0),1) #hline
		#show temp
		cv2.putText(heatmap,str(temp)+' C', (int(newWidth/2)+10, int(newHeight/2)-10),\
		cv2.FONT_HERSHEY_SIMPLEX, 0.45,(0, 0, 0), 2, cv2.LINE_AA)
		cv2.putText(heatmap,str(temp)+' C', (int(newWidth/2)+10, int(newHeight/2)-10),\
		cv2.FONT_HERSHEY_SIMPLEX, 0.45,(0, 255, 255), 1, cv2.LINE_AA)

		if hud==True:
			# display black box for our data
			cv2.rectangle(heatmap, (0, 0),(160, 120), (0,0,0), -1)
			# put text in the box
			cv2.putText(heatmap,'Avg Temp: '+str(avgtemp)+' C', (10, 14),\
			cv2.FONT_HERSHEY_SIMPLEX, 0.4,(0, 255, 255), 1, cv2.LINE_AA)

			cv2.putText(heatmap,'Label Threshold: '+str(threshold)+' C', (10, 28),\
			cv2.FONT_HERSHEY_SIMPLEX, 0.4,(0, 255, 255), 1, cv2.LINE_AA)

			cv2.putText(heatmap,'Colormap: '+cmapText, (10, 42),\
			cv2.FONT_HERSHEY_SIMPLEX, 0.4,(0, 255, 255), 1, cv2.LINE_AA)

			cv2.putText(heatmap,'Blur: '+str(rad)+' ', (10, 56),\
			cv2.FONT_HERSHEY_SIMPLEX, 0.4,(0, 255, 255), 1, cv2.LINE_AA)

			cv2.putText(heatmap,'Scaling: '+str(scale)+' ', (10, 70),\
			cv2.FONT_HERSHEY_SIMPLEX, 0.4,(0, 255, 255), 1, cv2.LINE_AA)

			cv2.putText(heatmap,'Contrast: '+str(alpha)+' ', (10, 84),\
			cv2.FONT_HERSHEY_SIMPLEX, 0.4,(0, 255, 255), 1, cv2.LINE_AA)


			cv2.putText(heatmap,'Snapshot: '+snaptime+' ', (10, 98),\
			cv2.FONT_HERSHEY_SIMPLEX, 0.4,(0, 255, 255), 1, cv2.LINE_AA)

			if recording == False:
				cv2.putText(heatmap,'Recording: '+elapsed, (10, 112),\
				cv2.FONT_HERSHEY_SIMPLEX, 0.4,(200, 200, 200), 1, cv2.LINE_AA)
			if recording == True:
				cv2.putText(heatmap,'Recording: '+elapsed, (10, 112),\
				cv2.FONT_HERSHEY_SIMPLEX, 0.4,(40, 40, 255), 1, cv2.LINE_AA)
		
		#Yeah, this looks like we can probably do this next bit more efficiently!
		#display floating max temp
		if maxtemp > avgtemp+threshold:
			cv2.circle(heatmap, (mrow*scale, mcol*scale), 5, (0,0,0), 2)
			cv2.circle(heatmap, (mrow*scale, mcol*scale), 5, (0,0,255), -1)
			cv2.putText(heatmap,str(maxtemp)+' C', ((mrow*scale)+10, (mcol*scale)+5),\
			cv2.FONT_HERSHEY_SIMPLEX, 0.45,(0,0,0), 2, cv2.LINE_AA)
			cv2.putText(heatmap,str(maxtemp)+' C', ((mrow*scale)+10, (mcol*scale)+5),\
			cv2.FONT_HERSHEY_SIMPLEX, 0.45,(0, 255, 255), 1, cv2.LINE_AA)

		#display floating min temp
		if mintemp < avgtemp-threshold:
			cv2.circle(heatmap, (lrow*scale, lcol*scale), 5, (0,0,0), 2)
			cv2.circle(heatmap, (lrow*scale, lcol*scale), 5, (255,0,0), -1)
			cv2.putText(heatmap,str(mintemp)+' C', ((lrow*scale)+10, (lcol*scale)+5),\
			cv2.FONT_HERSHEY_SIMPLEX, 0.45,(0,0,0), 2, cv2.LINE_AA)
			cv2.putText(heatmap,str(mintemp)+' C', ((lrow*scale)+10, (lcol*scale)+5),\
			cv2.FONT_HERSHEY_SIMPLEX, 0.45,(0, 255, 255), 1, cv2.LINE_AA)

		#display image
		cv2.imshow('Thermal',heatmap)

		#send the same picture to the virtual webcam
		if vcam is not None:
			vcam.send(cv2.cvtColor(fitToSize(heatmap, vcamWidth, vcamHeight), cv2.COLOR_BGR2RGB))

		if recording == True:
			elapsed = (time.time() - start)
			elapsed = time.strftime("%H:%M:%S", time.gmtime(elapsed)) 
			#print(elapsed)
			videoOut.write(heatmap)
		
		keyPress = cv2.waitKey(1)
		if keyPress == ord('a'): #Increase blur radius
			rad += 1
		if keyPress == ord('z'): #Decrease blur radius
			rad -= 1
			if rad <= 0:
				rad = 0

		if keyPress == ord('s'): #Increase threshold
			threshold += 1
		if keyPress == ord('x'): #Decrease threashold
			threshold -= 1
			if threshold <= 0:
				threshold = 0

		if keyPress == ord('d'): #Increase scale
			scale += 1
			if scale >=5:
				scale = 5
			newWidth = width*scale
			newHeight = height*scale
			if dispFullscreen == False and isPi == False:
				cv2.resizeWindow('Thermal', newWidth,newHeight)
		if keyPress == ord('c'): #Decrease scale
			scale -= 1
			if scale <= 1:
				scale = 1
			newWidth = width*scale
			newHeight = height*scale
			if dispFullscreen == False and isPi == False:
				cv2.resizeWindow('Thermal', newWidth,newHeight)

		if keyPress == ord('q'): #enable fullscreen
			dispFullscreen = True
			cv2.namedWindow('Thermal',cv2.WND_PROP_FULLSCREEN)
			cv2.setWindowProperty('Thermal',cv2.WND_PROP_FULLSCREEN,cv2.WINDOW_FULLSCREEN)
		if keyPress == ord('w'): #disable fullscreen
			dispFullscreen = False
			cv2.namedWindow('Thermal',cv2.WINDOW_GUI_NORMAL)
			cv2.setWindowProperty('Thermal',cv2.WND_PROP_AUTOSIZE,cv2.WINDOW_GUI_NORMAL)
			cv2.resizeWindow('Thermal', newWidth,newHeight)

		if keyPress == ord('f'): #contrast+
			alpha += 0.1
			alpha = round(alpha,1)#fix round error
			if alpha >= 3.0:
				alpha=3.0
		if keyPress == ord('v'): #contrast-
			alpha -= 0.1
			alpha = round(alpha,1)#fix round error
			if alpha<=0:
				alpha = 0.0


		if keyPress == ord('h'):
			if hud==True:
				hud=False
			elif hud==False:
				hud=True

		if keyPress == ord('m'): #m to cycle through color maps
			colormap += 1
			if colormap == 11:
				colormap = 0
				
		if keyPress == ord('j'): #m to cycle through color maps-
			colormap -= 1
			if colormap == 0:
				colormap = 11
		
		if keyPress == ord('r') and recording == False: #r to start reording
			videoOut = rec()
			recording = True
			start = time.time()
		if keyPress == ord('t'): #f to finish reording
			recording = False
			elapsed = "00:00:00"

		if keyPress == ord('p'): #f to finish reording
			snaptime = snapshot(heatmap)

		if keyPress == ord('q'):
			break
			capture.release()
			cv2.destroyAllWindows()
		

#clean up
cap.release()
if vcam is not None:
	vcam.close()
cv2.destroyAllWindows()
