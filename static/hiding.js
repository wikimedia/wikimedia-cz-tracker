( function () {
	function processHiddencomment( el ) {
		var hiddencomment = el.querySelector( '.hiddencomment' ),
			unhide = el.querySelector( 'a.unhide' );

		hiddencomment.hidden = true;
		unhide.hidden = false;

		unhide.addEventListener( 'click', function () {
			hiddencomment.hidden = false;
			unhide.hidden = true;
		} );
	}

	document.addEventListener( 'DOMContentLoaded', function () {
		document.querySelectorAll( '.hide-switch' ).forEach( function ( el ) {
			processHiddencomment( el );
		} );
	} );
}() );
