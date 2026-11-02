;;	cassimg__twelvebit.pro
;;	Convert image to twelve bits if 12-to-8 table was used
;;	Kevin Beurle	13th August 1998

PRO CassImg::TwelveBit

@cisscal_common.pro	; include COMMON definitions

;	If the image is already 12 bit (i.e. 12 to 8 conversion was not used)
;	then the conversion type attribute ConvType contains the value 12BIT
;	Conversion used for an image is documented by the ConvType attribute
;	of the image. Values are as follow:
;	Attribute
;	Value		Meaning
;	'12BIT'		Already a 12bit image: no conversion required
;	'TABLE'		12-8 pseudolog table was used: reconvert using LUT
;			(In this case, we also reconvert the bias vector)
;	'8LSB'		Image was truncated to 8LSB: no conversion required

IF DebugFlag gt 0 THEN BEGIN    
   CISSCAL_Log, '12-bit conversion:'
    IF self.ConvType EQ '12BIT' THEN BEGIN
        CISSCAL_Log, '  Image is 12-bit; no conversion needed.'
    ENDIF ELSE IF self.ConvType EQ 'TABLE' THEN BEGIN
        CISSCAL_Log, '  Table-encoded image: converting to 12-bit...'
    ENDIF ELSE IF self.ConvType EQ '8LSB' THEN BEGIN
        CISSCAL_Log, '  Image truncated to 8 least significant bits; no conversion needed.'
    ENDIF ELSE BEGIN
        CISSCAL_Log, '  Warning: unexpected Conversion Type value: ' + self.ConvType
    ENDELSE
ENDIF


IF self.ConvType EQ 'TABLE' THEN BEGIN
   *self.ImageP = cisscal_delut(*self.ImageP)


;	Update calibration history in image label:
;		(added by Ben Knowles, 11/04)
;               (revamped for CISSCAL 3.7, 5/13)

   newhistory='Converted from 8 to 12 bits'
   junk=self.Labels->Set('DATA_CONVERSION_TEXT',newhistory,1,/new)

ENDIF
   
END
