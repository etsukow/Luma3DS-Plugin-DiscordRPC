.SUFFIXES:

ifeq ($(strip $(DEVKITARM)),)
$(error "Please set DEVKITARM in your environment. export DEVKITARM=<path to>devkitARM")
endif

# Load optional local env configuration (IP_PC / UDP_PORT)
ifneq ("$(wildcard $(CURDIR)/.env)","")
include $(CURDIR)/.env
endif

IP_PC_RAW      := $(strip $(IP_PC))
UDP_PORT_RAW   := $(strip $(UDP_PORT))
DQ             := $(shell printf '"')
IP_PC_CLEAN    := $(subst $(DQ),,$(IP_PC_RAW))

ifeq ($(IP_PC_CLEAN),)
IP_PC_CLEAN := 127.0.0.1
endif

ifeq ($(UDP_PORT_RAW),)
UDP_PORT_RAW := 5005
endif

TOPDIR 		?= 	$(CURDIR)
include $(DEVKITARM)/3ds_rules

TARGET		:= 	discord-rpc
PLGINFO 	:= 	CTRPluginFramework.plgInfo
THREEGXTOOL := $(or $(strip $(THREEGXTOOL)),3gxtool)

BUILD		:= 	Build
INCLUDES	:= 	Includes
LIBDIRS		:= 	$(TOPDIR)
SOURCES 	:= 	Sources

SOC_OBJ_NAMES := \
	soc_accept.o soc_addglobalsocket.o soc_bind.o soc_closesocket.o soc_closesockets.o \
	soc_common.o soc_connect.o soc_fcntl.o soc_gai_strerror.o soc_getaddrinfo.o \
	soc_gethostbyaddr.o soc_gethostbyname.o soc_gethostid.o soc_gethostname.o soc_getipinfo.o \
	soc_getnameinfo.o soc_getnetworkopt.o soc_getpeername.o soc_getsockname.o soc_getsockopt.o \
	soc_herror.o soc_hstrerror.o soc_inet_addr.o soc_inet_aton.o soc_inet_ntoa.o \
	soc_inet_ntop.o soc_inet_pton.o soc_init.o soc_ioctl.o soc_listen.o soc_poll.o \
	soc_recvfrom.o soc_recv.o soc_select.o soc_send.o soc_sendto.o soc_setsockopt.o \
	soc_shutdown.o soc_shutdownsockets.o soc_sockatmark.o soc_socket.o

#---------------------------------------------------------------------------------
# options for code generation
#---------------------------------------------------------------------------------
ARCH		:=	-march=armv6k -mlittle-endian -mtune=mpcore -mfloat-abi=hard 

CFLAGS		:=	-Os -mword-relocations \
				-fomit-frame-pointer -ffunction-sections -fno-strict-aliasing \
				$(ARCH)

CFLAGS		+=	$(INCLUDE) -DARM11 -D_3DS \
				-DIP_PC_STR=\"$(IP_PC_CLEAN)\" \
				-DUDP_PORT_NUM=$(UDP_PORT_RAW)

CXXFLAGS	:= $(CFLAGS) -fno-rtti -fno-exceptions -std=gnu++11

ASFLAGS		:=	$(ARCH)
LDFLAGS		:= -T $(TOPDIR)/3ds.ld $(ARCH) -Os -Wl,-Map,$(notdir $*.map),--gc-sections 

LIBS		:= -lCTRPluginFramework

#---------------------------------------------------------------------------------
# no real need to edit anything past this point unless you need to add additional
# rules for different file extensions
#---------------------------------------------------------------------------------
ifneq ($(BUILD),$(notdir $(CURDIR)))
#---------------------------------------------------------------------------------

export OUTPUT	:=	$(CURDIR)/$(TARGET)
export TOPDIR	:=	$(CURDIR)
export VPATH	:=	$(foreach dir,$(SOURCES),$(CURDIR)/$(dir)) \
					$(foreach dir,$(DATA),$(CURDIR)/$(dir))

export DEPSDIR	:=	$(CURDIR)/$(BUILD)

CFILES			:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.c)))
CPPFILES		:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.cpp)))
SFILES			:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.s)))
#	BINFILES	:=	$(foreach dir,$(DATA),$(notdir $(wildcard $(dir)/*.*)))

export LD 		:= 	$(CXX)
export OFILES	:=	$(CPPFILES:.cpp=.o) $(CFILES:.c=.o) $(SFILES:.s=.o)
export INCLUDE	:=	$(foreach dir,$(INCLUDES),-I $(CURDIR)/$(dir) ) \
					$(foreach dir,$(LIBDIRS),-I $(dir)/include) \
					-I $(DEVKITPRO)/libctru/include \
					-I $(CURDIR)/$(BUILD)

export LIBPATHS	:=	$(foreach dir,$(LIBDIRS),-L $(dir)/Lib)

.PHONY: $(BUILD) clean all elf

#---------------------------------------------------------------------------------
all: $(BUILD)

elf:
	@[ -d $(BUILD) ] || mkdir -p $(BUILD)
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile $(OFILES) $(OUTPUT).elf

$(BUILD):
	@[ -d $@ ] || mkdir -p $@
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile $(OFILES) $(OUTPUT).3gx

#---------------------------------------------------------------------------------
clean:
	@echo clean ... 
	@rm -fr $(BUILD) $(OUTPUT).3gx

re: clean all

#---------------------------------------------------------------------------------

else

DEPENDS	:=	$(OFILES:.o=.d)
SOC_OBJ_DIR := $(TOPDIR)/$(BUILD)/libctru_soc
SOC_LINK_OBJS := $(addprefix $(SOC_OBJ_DIR)/,$(SOC_OBJ_NAMES))
SOC_EXTRACT_STAMP := $(SOC_OBJ_DIR)/.stamp
LIBS += $(SOC_LINK_OBJS)
.DEFAULT_GOAL := $(OUTPUT).3gx

$(SOC_EXTRACT_STAMP):
	@mkdir -p $(SOC_OBJ_DIR)
	@rm -f $(SOC_LINK_OBJS)
	@cd $(SOC_OBJ_DIR) && $(AR) x $(DEVKITPRO)/libctru/lib/libctru.a $(SOC_OBJ_NAMES)
	@touch $@

#---------------------------------------------------------------------------------
# main targets
#---------------------------------------------------------------------------------
$(OUTPUT).elf : $(SOC_EXTRACT_STAMP)
$(OUTPUT).3gx : $(OFILES)
$(OUTPUT).3gx : $(SOC_EXTRACT_STAMP)
#---------------------------------------------------------------------------------
# you need a rule like this for each extension you use as binary data
#---------------------------------------------------------------------------------
%.bin.o	:	%.bin
#---------------------------------------------------------------------------------
	@echo $(notdir $<)
	@$(bin2o)

#---------------------------------------------------------------------------------
%.3gx: %.elf
	@echo creating $(notdir $@)
	@command -v $(THREEGXTOOL) >/dev/null 2>&1 || { echo "Error: $(THREEGXTOOL) not found in PATH. Set THREEGXTOOL=/path/to/3gxtool"; exit 1; }
	@$(THREEGXTOOL) $(OUTPUT).elf $(TOPDIR)/$(PLGINFO) $@

-include $(DEPENDS)

#---------------------------------------------------------------------------------------
endif
