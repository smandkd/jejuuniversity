# pyPI: Potential Intensity Calculations in Python
# -----------------------------------------------------------------------------------
# Adapted from pcmin.m by Kerry Emanuel (ftp://texmex.mit.edu/pub/emanuel/TCMAX)
# Originally Updated by Daniel Gilford for
# Gilford et al. (2017) -- https://journals.ametsoc.org/doi/full/10.1175/JCLI-D-16-0827.1
# Gilford et al. (2019) -- https://journals.ametsoc.org/doi/10.1175/MWR-D-19-0021.1
# 
# Adapted for Python (pyPI/tcpypi) by Daniel Gilford, PhD (Rutgers U., daniel.gilford@rutgers.edu)
# Full pyPI documentation, module validation, and sample code provided at:
# ********************** https://github.com/dgilford/pyPI ***************************
#
# Download with the python Package index from the command line with:
#    > [missing url, please see most up to date version]
#
# Last updated 8/14/2020, v1.3
# -----------------------------------------------------------------------------------
#
# Revision History:
#   Revised on 9/24/2005 by K. Emanuel to fix convergence problems at high pressure
#     --Converted to MATLAB  5/17/2008
#   Revised 7/20/15 by D. Gilford to output the LNB
#   Revised 8/4/16 by D. Gilford to include lack of convergence if SST < 5C for TO/LNB
#   Revised 8/5/16 by D. Gilford to fix the "cape()" function output and include LNB
#   Revised 10/3/16 by D. Gilford to set LNB to the pressure-weighted crossing of buoyancy from negative to positive (the zero-line)
#   Revised 1/7/2017 by Luke Davis to fix and improper definition of JMIN, which should be the lowest profile level at or above the parcel level in the calculation of CAPE. Kerry is grateful to Luke and to Tim Merlis for pointing out this error. In practice, the error was usually less than 1 hPa in central pressure.    
#     --Converted to Python  04/2020
#   Revised 4/10/2020 by D. Rothenberg (daniel@danielrothenberg.com) for Numba optimization
#   Revised 4/13/2020 by D. Gilford to add new handling of missing profile data
#   Revised 6/17/2020 by D. Gilford for auxilary files
#   Revised 8/5/2020 by D. Gilford for auxilary files
#   Revised 8/14/2020 by D. Gilford for python packaging
#
# -----------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------
#

# import required packages
import numpy as np
import numba as nb
from . import constants
from . import utilities

# define the function to calculate CAPE
@nb.njit()
def cape(TP,RP,PP,T,R,P,ascent_flag=0,ptop=50,miss_handle=1):
    

#     function [CAPED,TOB,LNB,IFLAG]= cape(TP,RP,PP,T,R,P,ascent_flag=0,ptop=50,miss_handle=1)
#
#       This function calculates the CAPE of a parcel given parcel pressure PP (hPa), 
#       temperature TP (K) and mixing ratio RP (gram/gram) and given a sounding
#       of temperature (T in K) and mixing ratio (R in gram/gram) as a function
#       of pressure (P in hPa). CAPED is the calculated value of CAPE following
#       Emanuel 1994 (E94) Equation 6.3.6 and TOB is the temperature at the
#       level of neutral buoyancy ("LNB") for the displaced parcel. IFLAG is a flag
#       integer. If IFLAG = 1, routine is successful; if it is 0, routine did
#       not run owing to improper sounding (e.g. no water vapor at parcel level).
#       IFLAG=2 indicates that the routine did not converge, IFLAG=3 indicates that
#       the input profile had missing values.         
#
#  INPUT:   TP,RP,PP: floating point numbers of Parcel pressure (hPa), 
#             temperature (K), and mixing ratio (gram/gram)
#
#           T,R,P: One-dimensional arrays 
#             containing environmental pressure (hPa), temperature (K),
#             and mixing ratio (gram/gram) profiles. The arrays MUST be
#             arranged so that the lowest index corresponds
#             to the lowest model level, with increasing index
#             corresponding to decreasing pressure.
#
#           ascent_flag: Adjustable constant fraction for buoyancy of displaced  
#             parcels, where 0=Reversible ascent;  1=Pseudo-adiabatic ascent
#
#           ptop: Pressure below which sounding is ignored (hPa)
#
#           miss_handle: Flag that determines how missing (NaN) values are handled.
#             If = 0 (BE02 default), NaN values in profile are ignored and PI is still calcuated
#             If = 1 (pyPI default), given NaN values PI will be set to missing (with IFLAG=3)
#             NOTE: If any missing values are between the lowest valid level and ptop
#             then PI will automatically be set to missing (with IFLAG=3)
#
#
#  OUTPUT:  CAPED (J/kg) is Convective Available Potential Energy of an air parcel
#             consistent with its parcel and environmental properties.
#
#           TOB is the Temperature (K) at the level of neutral bouyancy 
#             for the displaced air parcel
#
#           LNB is the pressure level of neutral bouyancy (hPa) for the 
#             displaced air parcel
#
#           IFLAG is a flag where the value of 1 means OK; a value of 0
#             indicates an improper sounding or parcel; a value of 2
#             means that the routine failed to converge
#

    #
    #   ***  Handle missing values   ***
    #
    
    # find if any values are missing in the temperature or mixing ratio array
    valid_i=~np.isnan(T)
    first_valid=np.where(valid_i)[0][0]
    # Are there missing values? If so, assess according to flag
    if (np.sum(valid_i) != len(P)):
        # if not allowed, set IFLAG=3 and return missing CAPE
        if (miss_handle != 0):
            CAPED=np.nan
            TOB=np.nan
            LNB=np.nan
            IFLAG=3
            # Return the unsuitable values
            return(CAPED,TOB,LNB,IFLAG)
        else:
            # if allowed, but there are missing values between the lowest existing level
            # and ptop, then set IFLAG=3 and return missing CAPE
            if np.sum(np.isnan(T[first_valid:len(P)])>0):
                CAPED=np.nan
                TOB=np.nan
                LNB=np.nan
                IFLAG=3
                # Return the unsuitable values
                return(CAPED,TOB,LNB,IFLAG)
            else:
                first_lvl=first_valid
    else:
        first_lvl=0

    # Populate new environmental profiles removing values above ptop and
    # find new number, N, of profile levels with which to calculate CAPE
    N=np.argmin(np.abs(P-ptop))
    
    P=P[first_lvl:N]
    T=T[first_lvl:N]
    R=R[first_lvl:N]
    nlvl=len(P)
    TVRDIF = np.zeros((nlvl,))
    
    #
    #   ***  Run checks   ***
    #

    # CHECK: Is the input parcel suitable? If not, return missing CAPE
    if ((RP < 1e-6) or (TP < 200)):
        CAPED=0
        TOB=np.nan
        LNB=np.nan
        IFLAG=0
        # Return the unsuitable values
        return(CAPED,TOB,LNB,IFLAG)
    
    #
    #  ***  Define various parcel quantities, including reversible   ***
    #  ***                       entropy, S                          ***
    #                         
    TPC=utilities.T_ktoC(TP)                 # Parcel temperature in Celsius
    ESP=utilities.es_cc(TPC)                # Parcel's saturated vapor pressure
    EVP=utilities.ev(RP,PP)                 # Parcel's partial vapor pressure
    RH=EVP/ESP                              # Parcel's relative humidity
    RH=min([RH,1.0])                        # ensure that the relatively humidity does not exceed 1.0
    # calculate reversible total specific entropy per unit mass of dry air (E94, EQN. 4.5.9)
    S=utilities.entropy_S(TP,RP,PP)
    
    
    #
    #   ***  Estimate lifted condensation level pressure, PLCL   ***
    #     Based on E94 "calcsound.f" code at http://texmex.mit.edu/pub/emanuel/BOOK/
    #     see also https://psl.noaa.gov/data/composites/day/calculation.html
    #
    #   NOTE: Modern PLCL calculations are made following the exact expressions of Romps (2017),
    #   see https://journals.ametsoc.org/doi/pdf/10.1175/JAS-D-17-0102.1
    #   and Python PLCL code at http://romps.berkeley.edu/papers/pubdata/2016/lcl/lcl.py
    #
    PLCL=utilities.e_pLCL(TP,RH,PP)
    
    # Initial default values before loop
    CAPED=0
    TOB=T[0]
    IFLAG=1
    # Values to help loop
    NCMAX=0
    jmin=int(1e6)
    
    #
    #   ***  Begin updraft loop   ***
    #

    # loop over each level in the profile
    for j in range(nlvl):
        
        # jmin is the index of the lowest pressure level evaluated in the loop
        jmin=int(min([jmin,j]))
    
        #
        #   *** Calculate Parcel quantities BELOW lifted condensation level   ***
        #
        if (P[j] >= PLCL):
            # Parcel temperature at this pressure
            TG=TP*(P[j]/PP)**(constants.RD/constants.CPD)
            # Parcel Mixing ratio
            RG=RP
            # Parcel and Environmental Density Temperatures at this pressure (E94, EQN. 4.3.1 and 6.3.7)
            TLVR=utilities.Trho(TG,RG,RG)
            TVENV=utilities.Trho(T[j],R[j],R[j])
            # Bouyancy of the parcel in the environment (Proxy of E94, EQN. 6.1.5)
            TVRDIF[j,]=TLVR-TVENV
            
        #
        #   *** Calculate Parcel quantities ABOVE lifted condensation level   ***
        # 
        else:
            
            # Initial default values before loop
            TGNEW=T[j]
            TJC=utilities.T_ktoC(T[j])
            ES=utilities.es_cc(TJC)
            RG=utilities.rv(ES,P[j])
            
            #
            #   ***  Iteratively calculate lifted parcel temperature and mixing   ***
            #   ***                ratio for reversible ascent                    ***
            #
            
            # set loop counter and initial condition
            NC=0
            TG=0

            # loop until loop converges or bails out
            while ((np.abs(TGNEW-TG)) > 0.001):
            
                # Parcel temperature and mixing ratio during this iteration
                TG=TGNEW
                TC=utilities.T_ktoC(TG)
                ENEW=utilities.es_cc(TC)
                RG=utilities.rv(ENEW,P[j])
                
                # increase iteration count in the loop
                NC += 1
                
                #
                #   ***  Calculate estimates of the rates of change of the entropy    ***
                #   ***           with temperature at constant pressure               ***
                #

                ALV=utilities.Lv(TC)
                # calculate the rate of change of entropy with temperature, s_ell
                SL=(constants.CPD+RP*constants.CL+ALV*ALV*RG/(constants.RV*TG*TG))/TG
                EM=utilities.ev(RG,P[j])
                # calculate the saturated entropy, s_k, noting r_T=RP and
                # the last term vanishes with saturation, i.e. RH=1
                SG=(constants.CPD+RP*constants.CL)*np.log(TG)-constants.RD*np.log(P[j]-EM)+ALV*RG/TG
                # convergence speed (AP, step in entropy fraction) varies as a function of 
                # number of iterations
                if (NC < 3):
                    # converge slowly with a smaller step
                    AP=0.3
                else:
                    # speed the process with a larger step when nearing convergence
                    AP=1.0
                # find the new temperature in the iteration
                TGNEW=TG+AP*(S-SG)/SL
                
                #
                #   ***   If the routine does not converge, set IFLAG=2 and bail out   ***
                #
                if (NC > 500) or (ENEW > (P[j]-1)):
                    CAPED=0
                    TOB=T[0]
                    LNB=P[0]
                    IFLAG=2
                    # Return the uncoverged values
                    return(CAPED,TOB,LNB,IFLAG)
                
                # store the number of iterations
                NCMAX=NC
                
            #
            #   *** Calculate buoyancy   ***
            #
            # Parcel total mixing ratio: either reversible (ascent_flag=0) or pseudo-adiabatic (ascent_flag=1)
            RMEAN=ascent_flag*RG+(1-ascent_flag)*RP
            # Parcel and Environmental Density Temperatures at this pressure (E94, EQN. 4.3.1 and 6.3.7)
            TLVR=utilities.Trho(TG,RMEAN,RG)
            TENV=utilities.Trho(T[j],R[j],R[j])
            # Bouyancy of the parcel in the environment (Proxy of E94, EQN. 6.1.5)
            TVRDIF[j,]=TLVR-TENV
            

    #
    #  ***  Begin loop to find Positive areas (PA) and Negative areas (NA) ***
    #                  ***  and CAPE from reversible ascent ***
    NA=0.0
    PA=0.0
    
    #
    #   ***  Find maximum level of positive buoyancy, INB    ***
    #
    INB=0
    for j in range(nlvl-1, jmin, -1):
        if (TVRDIF[j] > 0):
            INB=max([INB,j])
            
    # CHECK: Is the LNB higher than the surface? If not, return zero CAPE  
    if (INB==0):
        CAPED=0
        TOB=T[0]
        LNB=P[INB]
#         TOB=np.nan
        LNB=0
        # Return the unconverged values
        return(CAPED,TOB,LNB,IFLAG)
    
    # if check is passed, continue with the CAPE calculation
    else:
    
    #
    #   ***  Find positive and negative areas and CAPE  ***
    #                  via E94, EQN. 6.3.6)
    #
        for j in range(jmin+1, INB+1, 1):
            PFAC=constants.RD*(TVRDIF[j]+TVRDIF[j-1])*(P[j-1]-P[j])/(P[j]+P[j-1])
            PA=PA+max([PFAC,0.0])
            NA=NA-min([PFAC,0.0])

    #
    #   ***   Find area between parcel pressure and first level above it ***
    #
        PMA=(PP+P[jmin])
        PFAC=constants.RD*(PP-P[jmin])/PMA
        PA=PA+PFAC*max([TVRDIF[jmin],0.0])
        NA=NA-PFAC*min([TVRDIF[jmin],0.0])
        
    #
    #   ***   Find residual positive area above INB and TO  ***
    #         and finalize estimate of LNB and its temperature
    #
        PAT=0.0
        TOB=T[INB]
        LNB=P[INB]
        if (INB < nlvl-1):
            PINB=(P[INB+1]*TVRDIF[INB]-P[INB]*TVRDIF[INB+1])/(TVRDIF[INB]-TVRDIF[INB+1])
            LNB=PINB
            PAT=constants.RD*TVRDIF[INB]*(P[INB]-PINB)/(P[INB]+PINB)
            TOB=(T[INB]*(PINB-P[INB+1])+T[INB+1]*(P[INB]-PINB))/(P[INB]-P[INB+1])
    
    #
    #   ***   Find CAPE  ***
    #            
        CAPED=PA+PAT-NA
        CAPED=max([CAPED,0.0])
        # set the flag to OK if procedure reached this point
        IFLAG=1
        # Return the calculated outputs to the above program level 
        return(CAPED,TOB,LNB,IFLAG)

    


# define the function to calculate PI
@nb.njit()
def pi(SSTC,MSL,P,TC,R,CKCD=0.9,ascent_flag=0,diss_flag=1,V_reduc=0.8,ptop=50,miss_handle=1):
    
#     function [VMAX,PMIN,IFL,TO,OTL] = pi(SSTC,MSL,P,TC,R,CKCD=0.9,ascent_flag=0,diss_flag=1,V_reduc=0.8,ptop=50,miss_handle=0)
#
#   ***    This function calculates the maximum wind speed         ***
#   ***             and mimimum central pressure                   ***
#   ***    achievable in tropical cyclones, given a sounding       ***
#   ***             and a sea surface temperature.                 ***
#
#   Thermodynamic and dynamic technical backgrounds (and calculations) are found in Bister 
#   and Emanuel (2002; BE02) and Emanuel's "Atmospheric Convection" (E94; 1994; ISBN: 978-0195066302)
#
#  INPUT:   SSTC: Sea surface temperature (C)
#
#           MSL: Mean Sea level pressure (hPa)
#
#           P,TC,R: One-dimensional arrays 
#             containing pressure (hPa), temperature (C),
#             and mixing ratio (g/kg). The arrays MUST be
#             arranged so that the lowest index corresponds
#             to the lowest model level, with increasing index
#             corresponding to decreasing pressure. The temperature
#             sounding should extend to at least the tropopause and 
#             preferably to the lower stratosphere, however the
#             mixing ratios are not important above the boundary
#             layer. Missing mixing ratios can be replaced by zeros
#
#           CKCD: Ratio of C_k to C_D (unitless number), i.e. the ratio
#             of the exchange coefficients of enthalpy and momentum flux
#             (e.g. see Bister and Emanuel 1998, EQN. 17-18). More discussion
#             on CK/CD is found in Emanuel (2003). Default is 0.9 based
#             on e.g. Wing et al. (2015)
#
#           ascent_flag: Adjustable constant fraction (unitless fraction) 
#             for buoyancy of displaced parcels, where 
#             0=Reversible ascent (default) and 1=Pseudo-adiabatic ascent
#
#           diss_flag: Adjustable switch integer (flag integer; 0 or 1)
#             for whether dissipative heating is 1=allowed (default) or 0=disallowed.
#             See Bister and Emanuel (1998) for inclusion of dissipative heating.
#
#           V_reduc: Adjustable constant fraction (unitless fraction) 
#             for reduction of gradient winds to 10-m winds see 
#             Emanuel (2000) and Powell (1980). Default is 0.8
#
#           ptop: Pressure below which sounding is ignored (hPa)
#
#           miss_handle: Flag that determines how missing (NaN) values are handled in CAPE calculation
#             If = 0 (BE02 default), NaN values in profile are ignored and PI is still calcuated
#             If = 1, given NaN values PI will be set to missing (with IFLAG=3)
#             NOTE: If any missing values are between the lowest valid level and ptop
#             then PI will automatically be set to missing (with IFLAG=3)
#
#  OUTPUT:  VMAX is the maximum surface wind speed (m/s)
#             reduced to reflect surface drag via V_reduc
#
#           PMIN is the minimum central pressure (hPa)
#
#           IFL is a flag: A value of 1 means OK; a value of 0
#             indicates no convergence; a value of 2
#             means that the CAPE routine failed to converge;
#             a value of 3  means the CAPE routine failed due to
#             missing data in the inputs
#
#           TO is the outflow temperature (K)
#
#           OTL is the outflow temperature level (hPa), defined as the level of neutral bouyancy 
#             where the outflow temperature is found, i.e. where buoyancy is actually equal 
#             to zero under the condition of an air parcel that is saturated at sea level pressure
#

    # convert units
    SSTK=utilities.T_Ctok(SSTC) # SST in kelvin
    T=utilities.T_Ctok(TC)      # Temperature profile in kelvin
    R=R*0.001                   # Mixing ratio profile in g/g

    # CHECK 1: do SSTs exceed 5C? If not, set IFL=0 and return missing PI
    if (SSTC <= 5.0):
        VMAX=np.nan
        PMIN=np.nan
        IFL=0
        TO=np.nan
        OTL=np.nan
        return(VMAX,PMIN,IFL,TO,OTL)

    # CHECK 2: do Temperature profiles exceed 100K? If not, set IFL=0 and return missing PI
    if (np.min(T) <= 100):
        VMAX=np.nan
        PMIN=np.nan
        IFL=0
        TO=np.nan
        OTL=np.nan
        return(VMAX,PMIN,IFL,TO,OTL)
    
    # Set Missing mixing ratios to zero g/g, following Kerry's BE02 algorithm
    R[np.isnan(R)]=0.
    
    # Saturated water vapor pressure
    # from Clausius-Clapeyron relation/August-Roche-Magnus formula
    ES0=utilities.es_cc(SSTC)

    # define the level from which parcels lifted (first pressure level)
    NK=0
    
    #
    #   ***   Find environmental CAPE *** 
    #
    TP=T[NK]
    RP=R[NK]
    PP=P[NK]
    result = cape(TP,RP,PP,T,R,P,ascent_flag,ptop,miss_handle)
    CAPEA = result[0]
    IFLAG = result[3]
    # if the CAPE function tripped a flag, set the output IFL to it
    if (IFLAG != 1):
        IFL=int(IFLAG)
    
    #
    #   ***   Begin iteration to find mimimum pressure   ***
    #
    
    # set loop counter and initial condition
    NP=0         # loop counter
    PM=970.0
    PMOLD=PM     # initial condition from minimum pressure
    PNEW=0.0     # initial condition from minimum pressure
    IFL=int(1)   # Default flag for CAPE calculation

    # loop until convergence or bail out
    while (np.abs(PNEW-PMOLD) > 0.5):
        
        #
        #   ***  Find CAPE at radius of maximum winds   ***
        #
        TP=T[NK]
        PP=min([PM,1000.0])
        # find the mixing ratio with the average of the lowest level pressure and MSL
        RP=constants.EPS*R[NK]*MSL/(PP*(constants.EPS+R[NK])-R[NK]*MSL)
        result = cape(TP,RP,PP,T,R,P,ascent_flag,ptop,miss_handle)
        CAPEM = result[0]
        IFLAG = result[3]
        # if the CAPE function tripped a different flag, set the output IFL to it
        if (IFLAG != 1):
            IFL=int(IFLAG)
        
        #
        #  ***  Find saturation CAPE at radius of maximum winds    ***
        #  *** Note that TO and OTL are found with this assumption ***
        #
        TP=SSTK
        PP=min([PM,1000.0])
        RP=utilities.rv(ES0,PP)
        result = cape(TP,RP,PP,T,R,P,ascent_flag,ptop,miss_handle)
        CAPEMS, TOMS, LNBS, IFLAG = result
        # if the CAPE function tripped a flag, set the output IFL to it
        if (IFLAG != 1):
            IFL=int(IFLAG)
        # Store the outflow temperature and level of neutral bouyancy at the outflow level (OTL)
        TO=TOMS   
        OTL=LNBS
        # Calculate the proxy for TC efficiency (BE02, EQN. 1-3)
        RAT=SSTK/TO
        # If dissipative heating is "off", TC efficiency proxy is set to 1.0 (BE02, pg. 3)
        if (diss_flag == 0):
            RAT=1.0
        
        #
        #  ***  Initial estimate of pressure at the radius of maximum winds  ***
        #
        RS0=RP
        # Lowest level and Sea-surface Density Temperature (E94, EQN. 4.3.1 and 6.3.7)
        TV0=utilities.Trho(T[NK],R[NK],R[NK])
        TVSST=utilities.Trho(SSTK,RS0,RS0)
        # Average Surface Density Temperature, e.g. 1/2*[Tv(Tsfc)+Tv(sst)]
        TVAV=0.5*(TV0+TVSST)
        # Converge toward CAPE*-CAPEM (BE02, EQN 3-4)
        CAT=(CAPEM-CAPEA)+0.5*CKCD*RAT*(CAPEMS-CAPEM)
        CAT=max([CAT,0.0])
        # Iterate on pressure
        PNEW=MSL*np.exp(-CAT/(constants.RD*TVAV))
        
        #
        #   ***  Test for convergence (setup for possible next while iteration)  ***
        #
        # store the previous step's pressure       
        PMOLD=PM
        # store the current step's pressure
        PM=PNEW
        # increase iteration count in the loop
        NP += 1
        
        #
        #   ***   If the routine does not converge, set IFL=0 and return missing PI   ***
        #
        if (NP > 200)  or (PM < 400):
            VMAX=np.nan
            PMIN=np.nan
            IFL=0
            TO=np.nan
            OTL=np.nan
            return(VMAX,PMIN,IFL,TO,OTL)
    
    # Once converged, set potential intensity at the radius of maximum winds
    CATFAC=0.5*(1.+1/constants.b)
    CAT=(CAPEM-CAPEA)+CKCD*RAT*CATFAC*(CAPEMS-CAPEM)
    CAT=max([CAT,0.0])
    
    # Calculate the minimum pressure at the eye of the storm
    # BE02 EQN. 4
    PMIN=MSL*np.exp(-CAT/(constants.RD*TVAV))
                 
    # Calculate the potential intensity at the radius of maximum winds
    # BE02 EQN. 3, reduced by some fraction (default 20%) to account for the reduction 
    # of 10-m winds from gradient wind speeds (Emanuel 2000, Powell 1980)
    FAC=max([0.0,(CAPEMS-CAPEM)])
    VMAX=V_reduc*np.sqrt(CKCD*RAT*FAC)
        
    # Return the calculated outputs to the above program level
    return(VMAX,PMIN,IFL,TO,OTL)
