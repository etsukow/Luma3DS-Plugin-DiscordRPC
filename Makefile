.SUFFIXES:

ifeq ($(strip $(DEVKITARM)),)
$(error "Please set DEVKITARM in your environment. export DEVKITARM=<path to>devkitARM")
endif

# Load optional local env configuration (DRPC_SERVER_WS_URL / UDP_PORT)
ifneq ("$(wildcard $(CURDIR)/.env)","")
include $(CURDIR)/.env
endif

# Extract IP from DRPC_SERVER_WS_URL (wss://1.2.3.4:5005 -> 1.2.3.4)
DQ             := $(shell printf '"')
_WS_URL_RAW    := $(strip $(DRPC_SERVER_WS_URL))
_WS_URL_CLEAN  := $(subst $(DQ),,$(subst wss://,,$(subst wss://,,$(strip $(_WS_URL_RAW)))))
# Strip port: keep everything before the last colon
IP_PC_CLEAN    := $(firstword $(subst :, ,$(_WS_URL_CLEAN)))
UDP_PORT_RAW   := $(strip $(UDP_PORT))

ifeq ($(IP_PC_CLEAN),)
IP_PC_CLEAN := 127.0.0.1
endif

ifeq ($(UDP_PORT_RAW),)
UDP_PORT_RAW := 5005
endif

TOPDIR      ?= $(CURDIR)
include $(DEVKITARM)/3ds_rules

TARGET      := default
PLGINFO     := discord-rpc.plgInfo
THREEGXTOOL := $(or $(strip $(THREEGXTOOL)),3gxtool)

BUILD       := Build
INCLUDES    := Includes
LIBDIRS     := $(CTRULIB)
SOURCES     := Sources

#---------------------------------------------------------------------------------
# options for code generation
#---------------------------------------------------------------------------------
ARCH        := -march=armv6k -mlittle-endian -mtune=mpcore -mfloat-abi=hard

CFLAGS      := -Os -mword-relocations \
                -fomit-frame-pointer -ffunction-sections -fno-strict-aliasing \
                $(ARCH)

CFLAGS      += $(INCLUDE) -D__3DS__ \
                -DIP_PC_STR=\"$(IP_PC_CLEAN)\" \
                -DUDP_PORT_NUM=$(UDP_PORT_RAW)

CXXFLAGS    := $(CFLAGS) -fno-rtti -fno-exceptions -std=gnu++11

ASFLAGS     := $(ARCH)
LDFLAGS     := -T $(TOPDIR)/3ds.ld $(ARCH) -Os -Wl,-Map,$(notdir $*.map),--gc-sections

LIBS        := -lctru

ifneq ($(BUILD),$(notdir $(CURDIR)))

export OUTPUT   := $(CURDIR)/$(TARGET)
export TOPDIR   := $(CURDIR)
export VPATH    := $(foreach dir,$(SOURCES),$(CURDIR)/$(dir)) \
                   $(foreach dir,$(DATA),$(CURDIR)/$(dir))

export DEPSDIR  := $(CURDIR)/$(BUILD)

CFILES          := plugin_main.c plgldr.c
SFILES          := bootloader.s csvc.s

export LD       := $(CXX)
export OFILES   := $(CFILES:.c=.o) $(SFILES:.s=.o)
export INCLUDE  := $(foreach dir,$(INCLUDES),-I $(CURDIR)/$(dir)) \
                   $(foreach dir,$(LIBDIRS),-I $(dir)/include) \
                   -I $(CURDIR)/$(BUILD)

export LIBPATHS := $(foreach dir,$(LIBDIRS),-L $(dir)/lib)

.PHONY: $(BUILD) clean all

all: $(BUILD)

$(BUILD):
	@[ -d $@ ] || mkdir -p $@
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile

clean:
	@echo clean ...
	@rm -fr $(BUILD) $(OUTPUT).3gx $(OUTPUT).elf

re: clean all

else

DEPENDS := $(OFILES:.o=.d)

$(OUTPUT).3gx : $(OFILES)

%.3gx: %.elf
	@echo creating $(notdir $@)
	@command -v $(THREEGXTOOL) >/dev/null 2>&1 || { echo "Error: $(THREEGXTOOL) not found in PATH. Set THREEGXTOOL=/path/to/3gxtool"; exit 1; }
	@$(THREEGXTOOL) $(OUTPUT).elf $(TOPDIR)/$(PLGINFO) $@

-include $(DEPENDS)

endif
