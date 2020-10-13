from pytest import approx, mark
import numpy as np
import sys

@mark.skipif(sys.platform != "linux", reason="S4 (RCWA) only installed for tests under Linux")
def test_planar_structure():

    # solcore imports
    from solcore.structure import Layer
    from solcore import material
    from solcore.absorption_calculator import calculate_rat, OptiStack

    # rayflare imports
    from rayflare.textures.standard_rt_textures import planar_surface
    from rayflare.structure import Interface, BulkLayer, Structure
    from rayflare.matrix_formalism.process_structure import process_structure
    from rayflare.matrix_formalism.multiply_matrices import calculate_RAT
    from rayflare.options import default_options

    # Thickness of bottom Ge layer
    bulkthick = 300e-6

    wavelengths = np.linspace(300, 1850, 50) * 1e-9

    # set options
    options = default_options()
    options.wavelengths = wavelengths
    options.project_name = 'method_comparison_test'
    options.n_rays = 250
    options.n_theta_bins = 3
    options.lookuptable_angles = 100
    options.parallel = True
    options.c_azimuth = 0.001

    # set up Solcore materials
    Ge = material('Ge')()
    GaAs = material('GaAs')()
    GaInP = material('GaInP')(In=0.5)
    Ag = material('Ag')()
    SiN = material('Si3N4')()
    Air = material('Air')()
    Ta2O5 = material('TaOx1')() # Ta2O5 (SOPRA database)
    MgF2 = material('MgF2')() # MgF2 (SOPRA database)

    front_materials = [Layer(120e-9, MgF2), Layer(74e-9, Ta2O5), Layer(464e-9, GaInP),
                       Layer(1682e-9, GaAs)]
    back_materials = [Layer(100E-9, SiN)]

    # TMM, matrix framework

    front_surf = Interface('TMM', layers=front_materials, name = 'GaInP_GaAs_TMM',
                           coherent=True)
    back_surf = Interface('TMM', layers=back_materials, name = 'SiN_Ag_TMM',
                          coherent=True)

    bulk_Ge = BulkLayer(bulkthick, Ge, name = 'Ge_bulk') # bulk thickness in m

    SC = Structure([front_surf, bulk_Ge, back_surf], incidence=Air, transmission=Ag)

    process_structure(SC, options)

    results_TMM_Matrix = calculate_RAT(SC, options)

    results_per_pass_TMM_matrix = results_TMM_Matrix[1]

    results_per_layer_front_TMM_matrix = np.sum(results_per_pass_TMM_matrix['a'][0], 0)

    ## RT with TMM lookup tables

    surf = planar_surface() # [texture, flipped texture]

    front_surf = Interface('RT_TMM', layers=front_materials, texture=surf, name = 'GaInP_GaAs_RT',
                           coherent=True)
    back_surf = Interface('RT_TMM', layers=back_materials, texture = surf, name = 'SiN_Ag_RT_50k',
                          coherent=True)

    SC = Structure([front_surf, bulk_Ge, back_surf], incidence=Air, transmission=Ag)

    process_structure(SC, options)

    results_RT = calculate_RAT(SC, options)

    results_per_pass_RT = results_RT[1]

    # only select absorbing layers, sum over passes
    results_per_layer_front_RT = np.sum(results_per_pass_RT['a'][0], 0)

    ## RCWA

    front_surf = Interface('RCWA', layers=front_materials, name = 'GaInP_GaAs_RCWA',
                           coherent=True, d_vectors = ((500,0), (0,500)), rcwa_orders=2)
    back_surf = Interface('RCWA', layers=back_materials, name = 'SiN_Ag_RCWA',
                          coherent=True, d_vectors = ((500,0), (0,500)), rcwa_orders=2)


    SC = Structure([front_surf, bulk_Ge, back_surf], incidence=Air, transmission=Ag)

    process_structure(SC, options)

    results_RCWA_Matrix = calculate_RAT(SC, options)

    results_per_pass_RCWA = results_RCWA_Matrix[1]

    # only select absorbing layers, sum over passes
    results_per_layer_front_RCWA = np.sum(results_per_pass_RCWA['a'][0], 0)


    ## pure TMM (from Solcore)
    all_layers = front_materials + [Layer(bulkthick, Ge)] + back_materials

    coh_list = len(front_materials)*['c'] + ['i'] + ['c']

    OS_layers = OptiStack(all_layers, substrate=Ag, no_back_reflection=False)

    TMM_res = calculate_rat(OS_layers, wavelength=wavelengths*1e9,
                            no_back_reflection=False, angle=options['theta_in']*180/np.pi, coherent=False,
                            coherency_list=coh_list, pol=options['pol'])

    # stack results for comparison
    TMM_reference = TMM_res['A_per_layer'][1:-2].T
    TMM_matrix = np.hstack((results_per_layer_front_TMM_matrix, results_TMM_Matrix[0].A_bulk[0].data[:,None]))
    RCWA_matrix = np.hstack((results_per_layer_front_RCWA, results_RCWA_Matrix[0].A_bulk[0].data[:, None]))
    RT_matrix = np.hstack((results_per_layer_front_RT, results_RT[0].A_bulk[0].data[:, None]))

    assert TMM_reference == approx(TMM_matrix, abs=0.01)
    assert TMM_reference == approx(RCWA_matrix, abs=0.01)
    assert TMM_reference == approx(RT_matrix, abs=0.15)



def test_absorption_profile():
    from rayflare.ray_tracing.rt import rt_structure
    from rayflare.textures import planar_surface
    from rayflare.options import default_options
    from solcore import material
    from solcore import si
    from rayflare.transfer_matrix_method.tmm import tmm_structure
    from solcore.structure import Layer

    Air = material('Air')()
    Si = material('Si')()
    GaAs = material('GaAs')()
    Ge = material('Ge')()

    triangle_surf = planar_surface()

    options = default_options()

    options.wavelengths = np.linspace(700, 1400, 2)*1e-9
    options.theta_in = 45*np.pi/180
    options.nx = 5
    options.ny = 5
    options.pol = 'p'
    options.n_rays = 2000
    options.depth_spacing = 1e-6


    rtstr = rt_structure(textures=[triangle_surf, triangle_surf, triangle_surf, triangle_surf],
                        materials = [GaAs, Si, Ge],
                        widths=[si('100um'), si('70um'), si('50um')], incidence=Air, transmission=Air)
    result_rt = rtstr.calculate(options)


    stack = [Layer(si('100um'), GaAs), Layer(si('70um'), Si), Layer(si('50um'), Ge)]

    strt = tmm_structure(stack, coherent=False, coherency_list=['i', 'i', 'i'],
                         no_back_reflection=False)

    output = strt.calculate(options['wavelengths'] * 1e9, angle=options['theta_in'], pol=options['pol'],
                            profile=True, depth_spacing=1000, layers=[1, 2, 3])

    tmm_profile = output['profile'][output['profile'] > 1e-8]
    rt_profile = result_rt['profile'][output['profile']> 1e-8]

    assert output['profile'].shape == result_rt['profile'].shape
    assert rt_profile == approx(tmm_profile, rel=0.2)
